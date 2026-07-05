---
title: Merger Lab API
emoji: 🏛️
colorFrom: yellow
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Merger Lab engine API — IC memo JSON/HTML for the web deal room
---

# MERGER LAB — API

FastAPI backend for the premium web deal room. A thin HTTP layer over the same
engine the Streamlit app uses: `POST /api/deal` runs the full stack (RBI 2026
guardrails, SEBI Takeover mechanics, optimizer, 10,000 Monte-Carlo paths, DCF,
trading comps, football field) and returns the rendered IC memo HTML plus
headline metrics.

- `GET /api/health` — status + available sectors
- `POST /api/deal` — `{acquirer, target, sector, premium_pct, ...}` → memo + metrics

Pure-compute, free public data (yfinance). **No LLM / API-token calls.** Not
investment advice. Full source: https://github.com/DogInfantry/merger-lab
