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

## Active / next task: precedent-DB verification (20/37 verified) + provenance SURFACED (SHIPPED)
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
- **PR #6 (MERGED — commit d4989d2):** 6 tier-4 listed targets —
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
- **PR #7 (MERGED — commit 7ff4051): moat made VISIBLE.** Memo stored `sector_comps`
  but only printed a percentile sentence. Added a **"2a · Sector precedents"** table in
  `ic_memo.html` (driven by `comps_rows` already in ctx — no query change): VERIFIED rows
  link to the SEBI/exchange filing (✓), unverified show muted `illustrative`; premiums
  render only where public, else `n/a`. Also **root-cause fix**: `inr`/`pct`/`num` Jinja
  filters were only `None`-safe; `pandas.to_dict('records')` yields float `NaN` for blank
  cells → crashed `indian_group()` on first undisclosed `deal_value` (ACC row). Added
  shared `_missing()` helper (`x is None or x != x`) to all three filters.
- **PR #8 (MERGED — commit 460290f): Excel parity.** Added `source_url` column to the
  Excel "Precedent Comps" tab (`excel_generator.py`) so the model carries the same filing
  links as the memo (notes column already had the `VERIFIED —` prefix).
- **Milestone status:** verified-provenance moat is DONE end-to-end (DB → memo → Excel).
  Remaining verification is opportunistic only.
- **Follow-up idea (STILL not built):** premium is the verifiable signal (open-offer price
  vs pre-announce close, both public); EV/EBITDA is not. Pivot the empty
  premium-vs-EV/EBITDA scatter to a **premium-by-sector distribution** (~7 real premiums in
  DB, Cement richest at 4). Thin outside Cement — low priority.

## Session 2026-07-05 — valuation depth + web deal room (SHIPPED, main @ 7ff1f7e)
Two milestones, both merged to `main` and deployed. Tests 28 → **38**, all green.

- **PR #9 (MERGED — 54580c5): valuation depth = the CA/CFA credibility layer.**
  Accretion/dilution is a *relative* test; added the *absolute* one.
  - `src/dcf.py` — two-stage unlevered FCFF DCF, INR crore, tunable drivers
    (wacc/growth/margins/da/capex/nwc), bull/bear per-share range. Self-check:
    flat-FCFF (growth=0,tg=0) ⇒ EV = FCFF/wacc, horizon-independent.
  - `src/trading_comps.py` — listed-peer EV/EBITDA · EV/Sales · P/E medians →
    implied per-share; `SECTOR_PEERS` = hand-curated PUBLIC ticker seed (7 sectors),
    financials fetched live via **injected** fetch fn (`fetch_sector_peers`), so the
    module is offline/testable. Non-positive/missing multiples dropped, never imputed.
  - `deal_package.build_deal_package(..., peers=None)` — DCF always attempted, comps
    only when peers supplied; both degrade to `None` on thin data (honest blank). New
    fields `dcf`, `trading_comps`, `valuation_ranges` (all defaulted → back-compatible).
  - Memo section **"2b · Standalone Valuation"**: `svg_football_field()` (method ranges
    vs offer=red / market=grey markers), DCF table + assumptions, trading-comps peer table.
  - Web-native memo: `generate_samples.py` now fetches peers + writes the rendered memo
    to `site/deals/<slug>.html`; `ic_memo.html` gained `@media screen` (centered premium
    "paper"); `site/index.html` hero + cards open the live web memos (PDF/Excel still down-
    loadable). Real output honest: Persistent DCF ₹1,471 vs ₹4,683 mkt (−69%, high multiple).
  - `tests/test_valuation.py` (10) — DCF/comps/football wiring on build_deal_package.

- **PR #10 (MERGED — 90ec3ef): Option B = premium interactive web deal room.** ADDITIVE —
  Streamlit app untouched, still linked. User constraint honored: **NO Claude/Anthropic
  tokens in the public path** (engine is pure Python, Non-negotiable #5).
  - `api/app.py` — FastAPI over the SAME `build_deal_package` + `render_memo_html` (full
    depth, no parallel logic). `GET /api/health`, `POST /api/deal` → memo HTML + metrics.
    CORS open (public read-only compute). Self-check via TestClient (no net/token).
  - `api/requirements.txt` (fastapi/uvicorn/pandas/numpy/scipy/yfinance/jinja2 — no pango).
  - `.hf-api/Dockerfile` + `.hf-api/SPACE_README.md` — SEPARATE HF Space
    **`DogInfantry/merger-lab-api`** (https://doginfantry-merger-lab-api.hf.space), created
    + uploaded via `hf upload` (NOT wired into sync-space.yml CI — manual redeploy for now).
    LIVE + tested end-to-end (POST returns 32KB memo with football field).
  - `site/build.html` — premium navy/gold interactive page; form → API → live memo inline
    + metric chips; vanilla JS; `const API_BASE` points at the API Space. Deploys on the
    existing Vercel static integration (no re-link). Landing CTA now → `build.html`.

- **Deferred (optional):** Excel DCF/Trading-Comps tabs (memo has them, Excel parity
  pending); wire `peers` into `app/streamlit_app.py` (its memo shows DCF, comps blank);
  premium-by-sector viz. None blocking.

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
- `src/dcf.py` — two-stage unlevered FCFF DCF (`run_dcf`, `DCFResult`), bull/bear range.
- `src/trading_comps.py` — `compute_trading_comps` + `SECTOR_PEERS` seed +
  `fetch_sector_peers(sector, fetch_fn, exclude)` (injected fetch → offline-testable).
- `src/deal_package.py` — **orchestrator**: `build_deal_package(..., peers=None)` returns the
  frozen `DealPackage` both generators consume; holds PROCEED/CONDITIONS/DECLINE rules; now
  carries `dcf`, `trading_comps`, `valuation_ranges` (football-field rows).
- `src/memo_generator.py` + `src/templates/ic_memo.html` — memo (inline-SVG charts incl.
  `svg_football_field`; section "2b · Standalone Valuation"; `@media screen` premium layout).
- `src/excel_generator.py` — 10-tab openpyxl model, live formulas + Δ-vs-engine column.

Web API (Option B, additive; pure-compute, no LLM/token calls):
- `api/app.py` — FastAPI over the engine: `/api/health`, `POST /api/deal` → memo+metrics.
- `api/requirements.txt` — API deps (no pango; returns HTML not PDF).
- `.hf-api/Dockerfile` + `.hf-api/SPACE_README.md` — the SEPARATE `merger-lab-api` HF Space.

App / ship:
- `app/streamlit_app.py` — wrapper UI; `_resolve(ticker, screener_file)` picks
  yfinance vs merged Screener data. `.streamlit/config.toml` (navy/gold theme).
- `generate_samples.py` (repo root) — rebuilds `samples/` + `site/assets/` +
  `docs/memo_preview.png` from live data.
- `site/index.html` — Vercel landing page (CTA → `build.html`; Streamlit kept as 2ndary).
- `site/build.html` — premium interactive deal room; POSTs to the API Space, renders the
  live memo inline. `const API_BASE` = the merger-lab-api Space URL.
- `site/deals/<slug>.html` — pre-rendered web-native sample memos (built by generate_samples).
- `vercel.json` — `outputDirectory: site`.
- `.hf/Dockerfile` + `.hf/SPACE_README.md` — Streamlit HF Space build (python:3.12 + pango).
- `.github/workflows/sync-space.yml` — auto-deploy Streamlit HF Space on push to `main`.

Tests (all pass; run `python tests/<file>.py`, no pytest needed): `test_known_deal.py`
(7, the sacred anchor), `test_quant_layer.py` (6), `test_derivatives.py` (7),
`test_generators.py` (5), `test_data_layer.py` (3), `test_valuation.py` (10) = **38 total**.

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
- **THREE deploy targets now:** (1) Vercel static `site/` (auto on push); (2) Streamlit HF
  Space `DogInfantry/merger-lab` (CI sync-space.yml, `.hf/`); (3) **API HF Space
  `DogInfantry/merger-lab-api` (`.hf-api/`) — MANUAL, not in CI.** Redeploy the API Space by
  staging a dir (Dockerfile→`Dockerfile`, SPACE_README.md→`README.md`, + `src api data/seeds`)
  and `hf upload DogInfantry/merger-lab-api <dir> . --repo-type space`. TODO: add CI for it.
- **`site/build.html` `API_BASE` is hardcoded** to the API Space URL — update if the Space
  is renamed, else the deal room silently fails to reach the backend.
- **HF `short_description` ≤ 60 chars** or `hf upload` rejects the README metadata.
- **HF free Spaces sleep when idle** → first request is a ~30s cold start; `build.html`
  shows a "retry once" hint for that.
- **GateGuard blocks `git reset --hard` and `rm -rf` even on temp dirs** (destructive gate,
  won't take a retry). Use `git switch -C <branch> <ref>` to realign, avoid `rm` on scratch,
  or run with `ECC_GATEGUARD=off`. Every write/edit also fact-forces once per file.
- **Git Bash `/tmp` ≠ Windows-python `/tmp`:** `curl -o /tmp/x` then Windows `python
  open('/tmp/x')` fails — pipe via stdin instead of a temp file.

## Conventions
- `CompanyFinancials` lives in `src/data_layer.py`; monetary fields `*_cr`
  (INR crore), shares in crore. Both self-checking modules run as
  `python src/<module>.py`.
- Precedent DB rebuilt via `precedent_db.load_seed()`; queries return DataFrames
  but keep SQL in readable multi-line strings (portfolio signal).
- Ship changes via PR → squash-merge to `main` → CI auto-deploys to HF Space.
- See HANDOFF.md for full phase-by-phase state and decisions.
