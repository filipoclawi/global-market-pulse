#!/usr/bin/env python3
"""Fetch and validate daily market history without an API key."""
from __future__ import annotations
import json, math, os, random, time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "market-data.json"
START_EPOCH = 0

MARKETS = [
    dict(id="msci-acwi", name="MSCI ACWI", region="Global", symbol="^892400-USD-STRD", currency="USD", kind="index", instrument="MSCI ACWI Index", benchmark="MSCI ACWI"),
    dict(id="sp500", name="S&P 500", region="United States", symbol="^GSPC", currency="USD", kind="index", instrument="S&P 500 Index", benchmark="S&P 500"),
    dict(id="msci-world-ex-usa", name="MSCI World ex USA", region="Developed ex-US", symbol="IDEV", currency="USD", kind="proxy", instrument="iShares Core MSCI International Developed Markets ETF", benchmark="MSCI World ex USA IMI"),
    dict(id="russell-2000", name="Russell 2000", region="United States", symbol="^RUT", currency="USD", kind="index", instrument="Russell 2000 Index", benchmark="Russell 2000"),
    dict(id="stoxx-europe-600", name="STOXX Europe 600", region="Europe", symbol="^STOXX", currency="EUR", kind="index", instrument="STOXX Europe 600 Index", benchmark="STOXX Europe 600"),
    dict(id="topix", name="TOPIX", region="Japan", symbol="1308.T", currency="JPY", kind="proxy", instrument="Listed Index Fund TOPIX ETF", benchmark="TOPIX"),
    dict(id="msci-emerging", name="MSCI Emerging Markets", region="Emerging markets", symbol="EEM", currency="USD", kind="proxy", instrument="iShares MSCI Emerging Markets ETF", benchmark="MSCI Emerging Markets"),
    dict(id="csi-300", name="CSI 300", region="China", symbol="000300.SS", provider="eastmoney", providerSymbol="1.000300", currency="CNY", kind="index", instrument="CSI 300 Index", benchmark="CSI 300"),
    dict(id="nifty-50", name="Nifty 50", region="India", symbol="^NSEI", currency="INR", kind="index", instrument="Nifty 50 Index", benchmark="Nifty 50"),
    dict(id="ibovespa", name="Ibovespa", region="Brazil", symbol="^BVSP", currency="BRL", kind="index", instrument="Ibovespa Index", benchmark="Ibovespa"),
]

class FetchError(RuntimeError): pass

def request_json(url: str, attempts: int = 4) -> dict:
    last = None
    for attempt in range(attempts):
        try:
            req = Request(url, headers={"User-Agent": "GlobalMarketPulse/1.0 (+public GitHub Pages dashboard)", "Accept": "application/json"})
            with urlopen(req, timeout=45) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt + 1 < attempts: time.sleep((2 ** attempt) + random.random())
    raise FetchError(f"request failed after {attempts} attempts: {last}")

def parse_chart(payload: dict, market: dict) -> list[list]:
    chart = payload.get("chart", {})
    if chart.get("error"): raise FetchError(f"{market['symbol']}: {chart['error']}")
    result = (chart.get("result") or [None])[0]
    if not result: raise FetchError(f"{market['symbol']}: no chart result")
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators", {})
    # Use raw closes for both indices and ETF proxies so every series measures
    # price return consistently. The chosen ETF proxies have clean split history.
    closes = ((indicators.get("quote") or [{}])[0].get("close") or [])
    points = {}
    for stamp, value in zip(timestamps, closes):
        if value is None or not math.isfinite(float(value)): continue
        day = datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
        points[day] = round(float(value), 6)
    ordered = [[day, points[day]] for day in sorted(points)]
    if len(ordered) < 30: raise FetchError(f"{market['symbol']}: only {len(ordered)} valid daily closes")
    return ordered

def parse_eastmoney(payload: dict, market: dict) -> list[list]:
    rows = (payload.get("data") or {}).get("klines") or []
    points = []
    for row in rows:
        fields = row.split(",")
        if len(fields) < 3: continue
        try: value = float(fields[2])
        except (TypeError, ValueError): continue
        if math.isfinite(value): points.append([fields[0], round(value, 6)])
    points.sort(key=lambda point: point[0])
    if len(points) < 30: raise FetchError(f"{market['providerSymbol']}: only {len(points)} valid daily closes")
    return points

def fetch_yahoo_points(market: dict, now: datetime) -> list[list]:
    params = urlencode({"period1": START_EPOCH, "period2": int((now + timedelta(days=1)).timestamp()), "interval": "1d", "events": "history", "includeAdjustedClose": "false"})
    symbol = quote(market["symbol"], safe="")
    errors = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try: return parse_chart(request_json(f"https://{host}/v8/finance/chart/{symbol}?{params}"), market)
        except FetchError as exc: errors.append(str(exc))
    raise FetchError("; ".join(errors))

def fetch_eastmoney_points(market: dict) -> list[list]:
    params = urlencode({"secid": market["providerSymbol"], "klt": 101, "fqt": 0, "lmt": 1000000, "end": 20500101, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"})
    return parse_eastmoney(request_json(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{params}"), market)

def fetch_market(market: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if market.get("provider") == "eastmoney":
        try:
            points = fetch_eastmoney_points(market)
        except FetchError as exc:
            print(f"Eastmoney unavailable for {market['name']}; using Yahoo fallback: {exc}", flush=True)
            points = fetch_yahoo_points(market, now)
    else:
        points = fetch_yahoo_points(market, now)
    previous, latest = points[-2], points[-1]
    change = ((latest[1] / previous[1]) - 1) * 100 if previous[1] else None
    fetched_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {**market, "fetchedAt": fetched_at, "latest": {"date": latest[0], "value": latest[1], "previousDate": previous[0], "previousClose": previous[1], "dayChangePct": round(change, 6) if change is not None else None}, "points": points}

def validate_document(document: dict) -> None:
    if document.get("schemaVersion") != 2: raise ValueError("unexpected schema version")
    if not document.get("generatedAt") or not document.get("dataAsOf"): raise ValueError("missing freshness metadata")
    series = document.get("indices") or []
    if len(series) != len(MARKETS): raise ValueError(f"expected {len(MARKETS)} markets, got {len(series)}")
    ids = [s["id"] for s in series]
    if len(ids) != len(set(ids)): raise ValueError("duplicate market ids")
    for item in series:
        points = item.get("points") or []
        if len(points) < 30: raise ValueError(f"{item['id']} has insufficient history")
        if points != sorted(points, key=lambda p: p[0]): raise ValueError(f"{item['id']} history is not sorted")
        if item["latest"]["date"] != points[-1][0]: raise ValueError(f"{item['id']} latest date mismatch")

def build_document(existing: dict | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    prior = {s["id"]: s for s in (existing or {}).get("indices", [])}
    series, stale = [], []
    for market in MARKETS:
        try:
            print(f"Fetching {market['name']} ({market['symbol']})...", flush=True)
            series.append(fetch_market(market, now))
        except Exception as exc:
            if market["id"] not in prior: raise
            cached = {**prior[market["id"]], **market}
            cached.setdefault("fetchedAt", (existing or {}).get("generatedAt") or (existing or {}).get("updatedAt"))
            series.append(cached); stale.append({"id": market["id"], "reason": str(exc)})
            print(f"Using previous valid data for {market['name']}: {exc}", flush=True)
    if len(stale) == len(MARKETS): raise FetchError("all market refreshes failed; preserving the last deployed dataset")
    generated_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    latest_dates = [item["latest"]["date"] for item in series]
    counts = Counter(latest_dates)
    data_as_of = max(counts, key=lambda date: (counts[date], date))
    doc = {"schemaVersion": 2, "generatedAt": generated_at, "dataAsOf": data_as_of, "refreshCadence": "Approximately every 6 hours", "source": "Yahoo Finance and Eastmoney public chart endpoints", "methodology": "Daily price closes for indices and ETF proxies; equal-weighted compounded daily price returns; closest close on or before comparison date.", "staleSeries": stale, "indices": series}
    validate_document(doc); return doc

def main() -> None:
    existing = None
    if OUTPUT.exists():
        try: existing = json.loads(OUTPUT.read_text())
        except (OSError, json.JSONDecodeError): pass
    document = build_document(existing)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")
    temp.replace(OUTPUT)
    print(f"Wrote {OUTPUT} with {len(document['indices'])} markets; stale={len(document['staleSeries'])}")

if __name__ == "__main__": main()
