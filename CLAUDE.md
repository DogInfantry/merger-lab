# MERGER LAB — Claude Code context

M&A accretion/dilution engine for Indian public markets. Product = IC memo PDF +
linked Excel model; Streamlit is a wrapper. Full spec:
`~/Downloads/MERGER_LAB_CLAUDE_CODE_SPEC.md`. Build phase by phase; update
HANDOFF.md at every phase boundary and stop for AR's review.

## Thesis
RBI acquisition-finance liberalization (amended 13 Feb 2026, effective 1 Apr
2026): banks may fund up to 75% of acquisition value; acquirer equity ≥ 25%;
consolidated D/E ≤ 3:1; acquirer net worth ≥ ₹500 Cr + 3-yr profitability.
These guardrails appear in the engine, optimizer, memo, Excel, and README.

## Non-negotiables
1. Memo + Excel are the product; dashboard is a wrapper.
2. Every number hand-verifiable; `tests/test_known_deal.py` is sacred (Phase 2).
3. No fabricated deal data — anything unverified is marked `ILLUSTRATIVE — verify`.
4. INR crore everywhere, Indian formatting (₹1,234 Cr), default tax 25.17%.
5. No paid APIs, no scraping, no LLM calls in the pipeline.
6. Typed functions, dataclasses, `methodology` docstring on every module.

## Phase status
- **Phase 1 (DONE):** `src/data_layer.py` (yfinance + Screener CSV fallback +
  24h JSON cache, INR-crore normalization), `src/precedent_db.py` (SQLite,
  raw-SQL window-function queries), `data/seeds/precedent_deals_seed.csv`
  (37 real India deals 2019–2025, numbers marked ILLUSTRATIVE).
- **Phase 2 (DONE):** deal.py, sources_uses.py (balance asserted), rbi_compliance.py
  (5 checks), sebi_sast.py (open offer + MPS + CCI), ppa.py, accretion_dilution.py
  (Y1–3 + break-even + heuristic cross-check), contribution.py, sensitivity.py,
  tests/test_known_deal.py (7/7, hand-derived arithmetic in comments).
- **Phase 3 (DONE):** optimizer.py (SLSQP multistart, real-engine objective,
  binding-constraint narrative), monte_carlo.py (10k iters, rng(42), point-mass
  == engine asserted), value_bridge.py (synergy PV vs premium, ROIC vs WACC,
  mechanical-accretion warning). tests/test_quant_layer.py 6/6.
- **Phase 4 (next):** collar.py (Black-Scholes put−call decomposition, yfinance
  realized vol), merger_arb.py (implied close probability).
- Phases 5–6: memo+Excel generators → Streamlit + samples + Vercel landing
  page + README.

## Conventions
- `CompanyFinancials` lives in `src/data_layer.py`; monetary fields `*_cr`
  (INR crore), shares in crore. Both self-checking modules run as
  `python src/<module>.py`.
- Precedent DB rebuilt via `precedent_db.load_seed()`; queries return DataFrames
  but keep SQL in readable multi-line strings (portfolio signal).
- See HANDOFF.md for current state and decisions.
