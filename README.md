# Global Market Pulse

A privacy-safe, static dashboard for ten global equity benchmarks. It refreshes approximately every six hours through GitHub Actions and is deployed with GitHub Pages.

## What it tracks

- MSCI ACWI — iShares ACWI ETF proxy
- S&P 500
- MSCI World ex USA — iShares UCITS ETF proxy
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
python3 -m unittest discover -s tests -p 'test_*.py'
node tests/test_market.js
python3 scripts/build_site.py
python3 -m http.server 8000
```

Open <http://localhost:8000>.

## Methodology

- Daily closes are fetched from Yahoo Finance's public chart endpoint. ETF proxies use adjusted closes so stock splits do not create false market moves.
- “Average change” is the equal-weighted arithmetic mean of each available market's percentage change from the closest market close on or before the chosen date to its latest close.
- Markets without history on the chosen date are excluded and coverage is shown.
- ETF proxies are used only when reliable free historical index feeds are unavailable.

Data is informational and may be delayed. It is not investment advice.
