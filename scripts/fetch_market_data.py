#!/usr/bin/env python3
"""Fetch and validate daily market history without an API key."""
from __future__ import annotations
import json, math, os, random, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "market-data.json"
START_EPOCH = int(datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp())

MARKETS = [
    dict(id="msci-acwi", name="MSCI ACWI", region="Global", symbol="ACWI", currency="USD", kind="proxy", instrument="iShares MSCI ACWI ETF", benchmark="MSCI ACWI"),
    dict(id="sp500", name="S&P 500", region="United States", symbol="^GSPC", currency="USD", kind="index", instrument="S&P 500 Index", benchmark="S&P 500"),
    dict(id="msci-world-ex-usa", name="MSCI World ex USA", region="Developed ex-US", symbol="XUSE.SW", currency="USD", kind="proxy", instrument="iShares MSCI World ex-USA UCITS ETF", benchmark="MSCI World ex USA"),
    dict(id="russell-2000", name="Russell 2000", region="United States", symbol="^RUT", currency="USD", kind="index", instrument="Russell 2000 Index", benchmark="Russell 2000"),
    dict(id="stoxx-europe-600", name="STOXX Europe 600", region="Europe", symbol="^STOXX", currency="EUR", kind="index", instrument="STOXX Europe 600 Index", benchmark="STOXX Europe 600"),
    dict(id="topix", name="TOPIX", region="Japan", symbol="1308.T", currency="JPY", kind="proxy", instrument="Listed Index Fund TOPIX ETF", benchmark="TOPIX"),
    dict(id="msci-emerging", name="MSCI Emerging Markets", region="Emerging markets", symbol="EEM", currency="USD", kind="proxy", instrument="iShares MSCI Emerging Markets ETF", benchmark="MSCI Emerging Markets"),
    dict(id="csi-300", name="CSI 300", region="China", symbol="000300.SS", currency="CNY", kind="index", instrument="CSI 300 Index", benchmark="CSI 300"),
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
    raw_closes = ((indicators.get("quote") or [{}])[0].get("close") or [])
    adjusted = ((indicators.get("adjclose") or [{}])[0].get("adjclose") or [])
    # ETF proxies need adjusted closes to remove artificial stock-split jumps.
    # Exact index series use the published benchmark close.
    closes = adjusted if market.get("kind") == "proxy" and len(adjusted) == len(timestamps) else raw_closes
    points = {}
    for stamp, value in zip(timestamps, closes):
        if value is None or not math.isfinite(float(value)): continue
        day = datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
        points[day] = round(float(value), 6)
    ordered = [[day, points[day]] for day in sorted(points)]
    if len(ordered) < 30: raise FetchError(f"{market['symbol']}: only {len(ordered)} valid daily closes")
    return ordered

def fetch_market(market: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    params = urlencode({"period1": START_EPOCH, "period2": int((now + timedelta(days=1)).timestamp()), "interval": "1d", "events": "history", "includeAdjustedClose": "true"})
    symbol = quote(market["symbol"], safe="")
    errors = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            points = parse_chart(request_json(f"https://{host}/v8/finance/chart/{symbol}?{params}"), market)
            break
        except FetchError as exc: errors.append(str(exc))
    else: raise FetchError("; ".join(errors))
    previous, latest = points[-2], points[-1]
    change = ((latest[1] / previous[1]) - 1) * 100 if previous[1] else None
    return {**market, "latest": {"date": latest[0], "value": latest[1], "previousDate": previous[0], "previousClose": previous[1], "dayChangePct": round(change, 6) if change is not None else None}, "points": points}

def validate_document(document: dict) -> None:
    if document.get("schemaVersion") != 1: raise ValueError("unexpected schema version")
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
            cached = prior[market["id"]
            ]
            series.append(cached); stale.append({"id": market["id"], "reason": str(exc)})
            print(f"Using previous valid data for {market['name']}: {exc}", flush=True)
    doc = {"schemaVersion": 1, "updatedAt": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"), "refreshCadence": "Approximately every 6 hours", "source": "Yahoo Finance public chart endpoint", "methodology": "Daily benchmark closes; adjusted closes for ETF proxies; equal-weighted percentage changes; closest close on or before comparison date.", "staleSeries": stale, "indices": series}
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
