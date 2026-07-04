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
- **Phase 4 (DONE):** collar.py (BS via math.erf, put−call collar decomposition,
  payoff grid, annualized_vol + realized_vol_yf), merger_arb.py (implied close
  probability, out-of-bounds flagged not clamped). tests/test_derivatives.py 7/7.
- **Phase 5 (DONE):** deal_package.py (orchestrator + recommendation rules),
  memo_generator.py + templates/ic_memo.html (inline-SVG charts, headless-Edge
  PDF on Windows / WeasyPrint elsewhere), excel_generator.py (10 tabs, live
  cross-referenced formulas, Δ-vs-engine tie-out column).
  tests/test_generators.py 5/5; 25 tests total green.
- **Phase 6 (DONE):** app/streamlit_app.py (form → RBI badges → results →
  download buttons), generate_samples.py (3 live-data sample deal rooms incl.
  honest DECLINEs), site/index.html (Vercel landing, STREAMLIT_APP_URL
  placeholder), README.md. USD-filer FX inference added to data_layer
  (Infosys 20-F bug). 28/28 tests.
- **SHIPPED (2026-07-03):** public GitHub repo
  https://github.com/DogInfantry/merger-lab; live HF Docker Space
  https://doginfantry-merger-lab.hf.space. CI `.github/workflows/sync-space.yml`
  auto-deploys to the Space on every push to `main` touching app/src/data/config.

## Post-ship maintenance (this session, 2026-07-03)
Two bugs/features shipped via PR → squash-merge → auto-deploy (all green, 28/28):
- **PR #1 (fix):** SQLite cross-thread crash. `get_connection()` opened SQLite
  with default `check_same_thread=True`; the app caches ONE connection across
  Streamlit reruns (which run on new threads) via `@st.cache_resource`. The
  connection is only queried when a sector is picked (deal_package.py:171
  `if precedent_conn is not None and sector:`) — so "—" worked but selecting a
  sector → `sqlite3.ProgrammingError` → whole app died. Fix: `check_same_thread
  =False` in `get_connection()` (read-only after one-time load_seed, so safe).
- **PR #2 (feat):** optional Screener.in CSV upload as yfinance fallback. Wired
  the already-built (but never-called) `load_screener_csv()` + `merge_financials()`
  into the app: two per-company `st.file_uploader`s in the sidebar form + a new
  module-level `_resolve(ticker, screener_file)` helper. Screener fundamentals
  override yfinance; price/shares still come from yfinance. Fixes app dead-ending
  when Yahoo data is stale/wrong.

## Active / next task: precedent-DB verification (IN PROGRESS — 20/37 verified, 17 ILLUSTRATIVE)
The 37 deals in `data/seeds/precedent_deals_seed.csv` started ALL marked
`ILLUSTRATIVE — verify` (fabricated numbers, generic source URLs). This is the
un-overlappable credibility moat. Rule #3 stands: no fabricated numbers —
unverifiable stays ILLUSTRATIVE. Agent CAN fetch public filings during dev
(research, not the forbidden runtime scraping). Verified rows carry note prefix
`VERIFIED —` + a real deal-specific `source_url`; analyst-only EV/EBITDA & P/E and
unverifiable premiums are BLANKED (honest-blank beats fake).

- **PR #3 (MERGED):** 4 marquee deals (5 rows) — L&T-Mindtree, PVR-INOX,
  HDFC Bank-HDFC Ltd (swap 42:25; deal_value 628000→304000 ≈ USD 40bn),
  Adani-Ambuja + Adani-ACC.
- **PR #4 (MERGED):** 6 tier-2 — HUL-GSK (swap 4.39:1; date 2019-12-01→2018-12-03),
  IDFC-IDFC First (reverse merger 155:100), Nirma-Glenmark (₹615/sh), Ambuja-Orient
  (open offer ₹395.40 = **12.27% verified premium**), JSW Paints-Akzo (₹3417.77 open
  offer), Torrent-JB Chem (SPA ₹1600 / open offer ₹1639.18 / merger 51:100).
  Side effect: no verified deal has BOTH a premium and an EV/EBITDA, so
  `premium_vs_multiple` is now honestly empty → its `__main__` self-check tolerates
  0 rows (query is self-check only, NOT wired into memo/deal_package).
- **PR #5 (MERGED — commit 8ade52e):** 3 tier-3 — JSW Steel-Bhushan
  Power (**stale-data fix: SC declared IBC plan illegal + ordered liquidation May 2025**),
  Mankind-BSV (date →2024-07-25), SMBC-Yes Bank 20% (date →2025-05-09; status →completed).
- **PR #6 (this branch `data/verify-tier4-precedents`):** 6 tier-4 listed targets —
  Bandhan-Gruh (swap 568:1000; blanked fake -7% premium + 45 P/E), Reliance-Just Dial
  (open offer Rs 1022.25 = 4.76% **discount** not +10% premium; blanked), Proximus-Route
  Mobile (57.56% at Rs 1626.40; blanked P/E), UltraTech-Kesoram (swap 1:52; premium set
  **24.1%** = Rs 173.15 vs Rs 139.45; deal 7600→5379; blanked EV/EBITDA), Axis-Citi
  (**announce_date 2023-03-30→2022-03-30**; closed ~Rs 11603 cr), Dalmia-JP
  (**stale-data**: 2022 framework fell through on JAL insolvency → fresh 2026 BTA
  Rs 2850 cr / 5.2 mtpa; status →withdrawn; blanked EV/EBITDA).
- **Next:** 17 rows still `ILLUSTRATIVE` — nearly all small/unlisted bolt-ons with NO
  public multiples, expected to STAY flagged (Tata Consumer ×3, Curatio, Capital Foods,
  Organic India, Zomato-Blinkit, Adani-Penna, Adani-GVK Mumbai airport, Tata-Neelachal,
  Sony-Zee + Aster-QCIL withdrawn/announced). Remaining verifiable listed-target
  candidates thin out here — Vedanta delisting (withdrawn), AU-Fincare (swap 579:2000),
  Ambuja-Sanghi, Adani-NDTV, Shriram merger. Diminishing returns; verify opportunistically.
- **Follow-up idea (not built):** premium is the verifiable signal (open-offer price vs
  pre-announce close, both public); EV/EBITDA is not. Pivot the empty
  premium-vs-EV/EBITDA scatter to a **premium-by-sector distribution** (9 real premiums
  now in the DB).

## File map
Engine (pure Python, INR crore, each has a `methodology` docstring + `__main__` self-check):
- `src/data_layer.py` — `CompanyFinancials` dataclass; `fetch_company()` (yfinance,
  24h JSON cache in `data/cache/`, `_statement_fx()` USD-filer inference),
  `load_screener_csv()`, `merge_financials()`.
- `src/precedent_db.py` — SQLite schema + `load_seed()` + 4 raw-SQL analysis queries.
- `src/deal.py` — `DealTerms`. `src/sources_uses.py` — `build_sources_uses` (balances).
- `src/ppa.py` — purchase-price accounting. `src/rbi_compliance.py` — 5 RBI checks.
- `src/sebi_sast.py` — open offer / MPS / creeping / CCI. `src/accretion_dilution.py`
  — `run_deal()` wrapper + Y1–3 engine + break-even. `src/contribution.py`,
  `src/sensitivity.py`.
- `src/optimizer.py` (SLSQP), `src/monte_carlo.py` (rng 42), `src/value_bridge.py`.
- `src/collar.py` (Black-Scholes), `src/merger_arb.py`.
- `src/deal_package.py` — **orchestrator**: `build_deal_package()` returns the frozen
  `DealPackage` both generators consume; holds the PROCEED/CONDITIONS/DECLINE rules.
- `src/memo_generator.py` + `src/templates/ic_memo.html` — PDF memo (inline-SVG charts).
- `src/excel_generator.py` — 10-tab openpyxl model, live formulas + Δ-vs-engine column.

App / ship:
- `app/streamlit_app.py` — wrapper UI; `_resolve(ticker, screener_file)` picks
  yfinance vs merged Screener data. `.streamlit/config.toml` (navy/gold theme).
- `generate_samples.py` (repo root) — rebuilds `samples/` + `site/assets/` +
  `docs/memo_preview.png` from live data.
- `site/index.html` — Vercel landing page. `vercel.json` — `outputDirectory: site`.
- `.hf/Dockerfile` + `.hf/SPACE_README.md` — HF Space build (python:3.12-slim + pango).
- `.github/workflows/sync-space.yml` — auto-deploy to HF Space on push to `main`.

Tests (all pass; run `python tests/<file>.py`, no pytest needed): `test_known_deal.py`
(7, the sacred anchor), `test_quant_layer.py` (6), `test_derivatives.py` (7),
`test_generators.py` (5), `test_data_layer.py` (3) = **28 total**.

## Gotchas
- **yfinance USD filers:** Infosys/Wipro (20-F) return statements in USD while
  price/EPS are INR → naive read gives −1000%+ accretion. `_statement_fx()` handles
  it; if you add companies, sanity-check accretion isn't wildly off.
- **SQLite + Streamlit threads:** `get_connection()` uses `check_same_thread=False`
  because the app shares one cached connection across reruns (new threads). Safe only
  because usage is read-only after `load_seed()`. Don't add writes on that connection.
- **`gh secret set` from PowerShell:** piping a token in adds a UTF-16 BOM that
  corrupts the secret. Pass via `--body` instead.
- **PDF engine differs by OS:** headless Edge/Chrome on Windows (no page numbers),
  WeasyPrint on Linux/HF Space (has page numbers). Both go through `html_to_pdf()`.
- **HF Space is a separate git repo** from GitHub (its own Dockerfile + frontmatter
  README under `.hf/`). CI syncs it; manual redeploy = `hf upload DogInfantry/merger-lab`.
- **`hf.exe` not on PATH:** it lives at `%APPDATA%\Python\Python314\Scripts\hf.exe`.
- **`streamlit` not on PATH:** run via `python -m streamlit run app/streamlit_app.py`.
- Python 3.14 local; Space uses 3.12. p75 premium is NaN for sectors with <4 deals
  (expected — NTILE(4) on thin data, not a bug).

## Conventions
- `CompanyFinancials` lives in `src/data_layer.py`; monetary fields `*_cr`
  (INR crore), shares in crore. Both self-checking modules run as
  `python src/<module>.py`.
- Precedent DB rebuilt via `precedent_db.load_seed()`; queries return DataFrames
  but keep SQL in readable multi-line strings (portfolio signal).
- Ship changes via PR → squash-merge to `main` → CI auto-deploys to HF Space.
- See HANDOFF.md for full phase-by-phase state and decisions.
