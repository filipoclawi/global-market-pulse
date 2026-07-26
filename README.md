# Global Market Pulse

A privacy-safe, static dashboard with a weekly macro-news inbox and ten global equity benchmarks. It refreshes approximately every six hours through GitHub Actions and is deployed with GitHub Pages.

## Weekly macro news

The default `News` tab keeps a small rolling set of high-signal economic stories for long-term diversified investors. Each item is intentionally short and includes a separate allocation lens rather than a trading call.

- New stable story IDs begin unread.
- Opening or explicitly marking an article changes its read state.
- Stars create a local saved collection; stories that leave the weekly inbox remain available to that collection for up to 180 days.
- Read and star state stays only in the visitor's browser via `localStorage`; it is never uploaded and there are no accounts or analytics.
- The generated artifact combines a reviewed editorial seed with strictly ranked releases and reports from the Federal Reserve, European Central Bank, U.S. Bureau of Economic Analysis, Bank of England, NPR and BBC News.
- Feed failures preserve the last valid artifact without blocking market-data deployment. A failed or underfilled refresh is written as an explicit stale-briefing state; `checkedAt`, `lastAttemptAt` and the latest story date remain separate.
- Automated story identity is based on the cleaned canonical source URL, so headline corrections and tracking-query changes do not reset read/star state.

## What it tracks

- MSCI ACWI
- S&P 500
- MSCI World ex USA — iShares IDEV ETF proxy (broader MSCI World ex USA IMI)
- Russell 2000
- STOXX Europe 600
- TOPIX — Listed Index Fund TOPIX ETF proxy
- MSCI Emerging Markets — iShares EEM ETF proxy
- CSI 300
- Nifty 50
- Ibovespa

Proxy use is shown directly in the interface. All change calculations are percentage based, so different currencies and index levels can be compared without conversion.

## Local use

```bash
python3 scripts/fetch_market_data.py
python3 scripts/fetch_economic_news.py
python3 -m unittest discover -s tests -p 'test_*.py'
node tests/test_market.js
python3 scripts/build_site.py
python3 -m http.server 8000
```

Open <http://localhost:8000>.

## Methodology

- Daily price closes are fetched from Yahoo Finance and Eastmoney public chart endpoints.
- “Average change” is the equal-weighted arithmetic mean of each available market's percentage change from the closest market close on or before the chosen date to its latest close.
- Markets without history on the chosen date are excluded and coverage is shown.
- The historical pulse compounds equal-weighted daily price returns. A newly available series joins without changing the level on its entry date, avoiding artificial jumps from constituent-history changes.
- ETF proxies are used only when reliable free historical index feeds are unavailable. The World ex USA proxy follows the broader IMI benchmark, which also includes small caps.

Data is informational and may be delayed. It is not investment advice.
