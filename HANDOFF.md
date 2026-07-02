# HANDOFF — living state doc

## Current status: Phase 6 COMPLETE (2026-07-02) — ALL PHASES DONE, awaiting AR ship review

### Phase 6 completed
- `app/streamlit_app.py` — sidebar form (tickers, premium, stake, mix, rates,
  synergies, acceptance, WACC, attestation) → RBI PASS/FAIL badge panel →
  A/D + contribution + MC histogram + collar payoff + heat sensitivity tabs →
  two primary download buttons (memo PDF, Excel). Nothing computed in the app
  itself — it wraps build_deal_package(). Dark navy/gold theme in
  `.streamlit/config.toml`; `packages.txt` carries WeasyPrint's apt deps for
  Streamlit Cloud (Linux).
- `generate_samples.py` (repo root) — regenerates all three sample deal rooms
  from live yfinance data, refreshes `site/assets/`, captures
  `docs/memo_preview.png` via headless Edge for the README.
- `samples/` — Project Horizon (INFY→PERSISTENT, 60% stock, DECLINE −23.8%),
  Project Bastion (ULTRACEMCO→JKCEMENT, 64% block + open offer, DECLINE),
  Project Meridian (HINDALCO→NATIONALUM, 51%+offer, 100% cash, PROCEED WITH
  CONDITIONS +2.15% Y1, P(Y2) 100%). All labeled ILLUSTRATIVE.
- `site/index.html` — single-file Vercel landing page: embedded hero memo PDF,
  three sample cards with verdict tags, "Run your own deal" CTA
  (STREAMLIT_APP_URL placeholder), 8 methodology stat boxes, disclaimer footer.
- `README.md` — spec order: memo screenshot first, RBI thesis, deliverables,
  sample table, module map, zero-paid-APIs, methodology, how-to-run,
  limitations, roadmap.

### Phase 6 bug found & fixed (important)
- **USD-filer currency mismatch:** yfinance returns Infosys statements in USD
  (20-F) while price/EPS are INR → first sample run produced Y1 −1215%.
  Fix: `_statement_fx()` in data_layer infers the FX factor from
  trailingEps × shares vs netIncomeToCommon (≈ USDINR 92.2 live), applied to
  all statement-scope fields, only when Yahoo declares differing currencies
  and the factor lands in a plausible 10–150 band. Poisoned cache cleared.
  3 new offline tests in tests/test_data_layer.py.

### Phase 6 verification
- 28/28 tests green (known-deal 7, quant 6, derivatives 7, generators 5,
  data-layer 3); app compiles; headless Streamlit served HTTP 200 locally.
- Sample generation script runs end-to-end from repo root (live data).
- NOT yet done (needs AR): Streamlit Cloud deploy + download-button click
  test in browser; set STREAMLIT_APP_URL + GitHub URL in site/index.html;
  `vercel site/` deploy; mobile render check; push repo to GitHub.

### Phase 5 completed
- `src/deal_package.py` (new orchestrator, not in spec file list — justified:
  memo and Excel must consume ONE frozen result set so they can never
  disagree). Runs SAST → per-scenario S&U → RBI → A/D → contribution →
  optimizer → MC → value bridge → collar (stock deals w/ vol) → precedent
  percentile. Mechanical recommendation rules documented in docstring
  (DECLINE / PROCEED WITH CONDITIONS / PROCEED).
- `src/memo_generator.py` + `src/templates/ic_memo.html` — Pyramid-principle
  memo, all 7 spec sections + 5.5. Navy #070B14 / gold #C9A84C, IBM Plex,
  fixed footer band "MERGER LAB · DogInfantry · CONFIDENTIAL — ILLUSTRATIVE".
  Charts are Python-generated inline SVG (MC histogram, collar payoff) — no
  matplotlib. Heat-styled sensitivity tables. Indian formatting filters
  (₹6,28,000 Cr). PDF chain: WeasyPrint if importable → headless Edge/Chrome
  --print-to-pdf (Windows path) → HTML fallback with warning. Page numbers
  only under WeasyPrint (Chromium margin-box limitation, documented).
- `src/excel_generator.py` — 10 tabs. Assumptions (blue-font hardcodes) is
  the single input source; S&U (3 acceptance-scenario formula columns +
  balance-check row), PPA, Pro-Forma P&L, Accretion-Dilution, Contribution,
  Value Bridge, Regulatory (PASS/FAIL as live =IF() formulas) are ALL real
  cross-referencing Excel formulas. Accretion-Dilution has a "Δ vs engine"
  column (formula − frozen Python value; displays 0 → in-file tie-out
  proof). Sensitivity + Precedent Comps are engine values (formulas would
  need 99 model copies) with ColorScale conditional formatting.
- `tests/test_generators.py` — 5 tests.

### Phase 5 verification results (all pass)
- Memo renders every section (asserted needle-by-needle), no unrendered
  Jinja; PDF via headless Edge = valid %PDF header, 317 KB, vector SVG.
- Excel: all 10 tabs present; S&U/A-D/P&L/Regulatory cells verified to be
  formulas (start with "=", =IF() for PASS/FAIL); engine tie-out column
  present; offer price hardcode = 60.0 on Assumptions.
- Package: toy deal at 100% acceptance → total uses 1,534.68 Cr hand-checked
  (1,200 + 312 open offer + 1.5% × 1,512 fees = 22.68).
- Full regression: 7 + 6 + 7 + 5 = 25 tests green.
- Dev outputs in samples/dev/ (toy deal — real large-cap samples are Phase 6).

### Phase 5 decisions
- deal_package.py added beyond spec file list (single source of truth for
  both generators).
- WeasyPrint not installed on Windows (GTK pain); headless Edge is the
  default PDF engine here. WeasyPrint path kept for Linux/Streamlit Cloud.
- AR manual check recommended: open project_anchor_model.xlsx, change an
  assumption (e.g. offer price), watch S&U/A-D recalc and Δ-engine column
  move off 0; open memo PDF and check typography/pagination.

### Phase 4 completed
- `src/collar.py` — Black-Scholes call/put (math.erf, no scipy dependency;
  σ=0 or T=0 branch returns discounted intrinsic exactly). Collar decomposed
  as: target long put at floor, short call at cap; value per target share
  = R × (P(floor) − C(cap)). Payoff DataFrame (fixed-ratio vs collared =
  R × clip(S, floor, cap)) for the memo chart. Plain-English explanation
  paragraph generated. `annualized_vol()` (pure) + `realized_vol_yf()`
  (yfinance daily log returns × √252). No-dividend simplification documented.
- `src/merger_arb.py` — implied close probability
  p = (P×(1+r)^t − D)/(O − D), annualized return if close, gross spread;
  p outside [0,1] flagged in narrative (bump expected / downside too high),
  not clamped.
- `tests/test_derivatives.py` — 7 tests.

### Phase 4 verification results (all pass)
- BS matches textbook hand-check (S=K=100, r=5%, σ=20%, T=1 → call 10.4506,
  put 5.5735, derivation in comments); put-call parity to 1e-9 across cases.
- Zero-vol collar → intrinsic only (0 inside the band).
- Collar payoff identity: collared value = R × clip(S, floor, cap); below
  floor the collared value strictly exceeds fixed-ratio value.
- Arb: offer = price at r=0 → p = 100% exactly; with 7% carry p = 1.172
  (= 1 + carry/(O−D)) and the "sweetened offer" flag fires. Hand example
  (95/100/80, 6m) → p = 0.75, annualized 10.8%.
- Live: RELIANCE.NS realized vol 20.1% (sane vs India VIX mid-teens–20s).
- Full regression: 7 known-deal + 6 quant-layer still pass.

### Phase 4 notes
- One test bound fixed during dev (carry effect on implied p is amplified by
  narrow O−D spread — module was right, initial test bound was wrong).

### Phase 3 completed
- `src/optimizer.py` — SLSQP multistart over (pct_cash, pct_debt_of_cash);
  pct_stock implied. Each evaluation runs the REAL engine (no surrogate).
  Constraints: RBI 75% debt cap, 25% equity floor, 3.0x pro-forma D/E, plus
  balance-sheet-cash availability and optional dilution ceiling. Reports
  binding constraints for the memo narrative; net-worth/profitability checks
  (mix-independent) reported separately via rbi_compliance.
- `src/monte_carlo.py` — 10k iters, `default_rng(42)`. Synergies triangular
  (50/100/130% of base), integration costs lognormal (mean = base), phase-in
  delay discrete {0: 70%, 1: 30%}. Structure (S&U/PPA/shares) fixed; NI
  recomputed with the same formula as the engine → point-mass config
  reproduces deterministic result to 1e-9 (asserted). Returns P(Y2
  accretive), P5/P50/P95 for Y1/Y2, raw samples for histograms, and
  `memo_line()` in the spec's format.
- `src/value_bridge.py` — synergy PV (after-tax perpetuity at WACC, 0% g),
  control premium on shares actually acquired, net value created; mechanical-
  accretion warning (Y1 accretive + negative bridge → "P/E arbitrage");
  incremental ROIC (owned target NI + run-rate synergies after tax over total
  Uses) vs WACC.
- `ADResult` gained `owned_frac` field (value bridge needs it).
- `tests/test_quant_layer.py` — 6 tests reusing the toy deal.

### Phase 3 verification results (all pass)
- Optimizer respects constraints: with cheap debt the 75% RBI cap binds and
  is reported binding; dilution ceiling respected when stock is attractive;
  optimum always ≥ base mix. Toy-deal optimum: 100% cash from balance sheet
  → Y1 +3.70% (vs −0.83% base), interior optimum (no guardrail binds — the
  toy acquirer is cash-rich).
- Value bridge sanity law: zero synergies + 20% premium → −200 Cr (premium
  hand-checked: (60−50)×20 = 200). Mechanical-accretion warning fires on an
  all-stock, zero-synergy P/E-arbitrage deal that is +Y1 accretive.
- MC point mass == deterministic engine to 1e-9; same seed → identical
  arrays. Toy deal: P(Y2 accretive) = 100%, Y1 P5 −3.7% / P95 +0.0%.
- Phase 2 known-deal suite still 7/7.

### Phase 2 completed
- `src/deal.py` — `DealTerms` dataclass (validates pct_cash+pct_stock=100);
  `CompanyFinancials` imported from data_layer, not redefined.
- `src/sources_uses.py` — S&U with open-offer cost as an extra Use; stock
  applies to negotiated consideration only, open offer is cash-settled;
  `pct_new_debt_of_cash_portion` applies to TOTAL cash needs (consideration
  + open offer + refinance + fees). Balance asserted to the rupee.
- `src/rbi_compliance.py` — 5 checks (75% debt cap, 25% equity, 3.0x pro-forma
  D/E, ₹500 Cr net worth, attested profitability) with value/threshold/status/
  explanation each; report goes verbatim into memo later.
- `src/sebi_sast.py` — 25% trigger → 26% open offer at offer price (floor-price
  simplification documented), 0/50/100% acceptance scenarios, MPS >75% breach
  flag, creeping-acquisition note, CCI ₹2,000 Cr deal-value flag.
- `src/ppa.py` — write-up on excess over owned book, DTL at tax rate, goodwill,
  straight-line incremental D&A.
- `src/accretion_dilution.py` — Y1–3 engine per spec formula; analytic
  break-even synergies; earnings-yield vs financing-cost heuristic cross-check
  with disagreement flag. `run_deal()` wrapper = S&U → PPA → A/D in one call.
- `src/contribution.py` — revenue/EBITDA/NI contribution vs pro-forma
  ownership, >10pt divergence flag.
- `src/sensitivity.py` — premium×synergies and cash×premium grids; each cell
  re-runs the full engine (no shortcut algebra).
- `tests/test_known_deal.py` — toy deal "Project Anchor", every expected value
  hand-derived in comments; 7 tests, all pass to 0.1%.

### Phase 2 verification results (all pass)
- `python tests/test_known_deal.py` → 7/7 PASS: S&U balances (1,218 Cr),
  PPA (goodwill 490 Cr, D&A 28 Cr), A/D Y1 −0.83% / Y2 +2.93% / Y3 +4.03%,
  break-even synergies 68.80 Cr (re-running at break-even → 0.000% Y1),
  sanity law (9% debt accretive / 14% debt dilutive vs 10% target yield),
  RBI fails 90%-debt deal, SAST 51% triggers offer + 77% holding breaches
  MPS + 312 Cr offer cost flows into Uses, contribution ties by hand.
- Sensitivity grids: 9×9 and 11×9, monotonic in premium and synergies.

### Phase 2 modeling decisions
- Partial-stake deals consolidate owned% of target NI (economic view, no
  minority-interest line) — documented in accretion_dilution methodology.
- Open offer consideration is cash-only (SAST offers modeled as cash).
- Standalone acquirer EPS held flat Y1–3 (isolates deal effects).
- Heuristic disagreement is a flag with reconciling-items note, not an error.

### Completed
- Directory scaffold per spec; `requirements.txt` (WeasyPrint excluded on
  Windows via env marker, fpdf2 listed as fallback).
- `src/data_layer.py`
  - `fetch_company(ticker)` via yfinance: price, shares, mcap, EPS, P/E, NI,
    revenue, EBITDA, debt, cash, net debt, interest expense, book value,
    effective tax rate (from income stmt, clamped 0–45%, else 25.17% default).
    All INR crore. 24h JSON cache in `data/cache/`. Missing fields → None +
    logged warning, never fabricated.
  - `load_screener_csv(path)`: label-scan parser (Sales, Net Profit, Operating
    Profit→EBITDA, Borrowings, Interest, EPS, Tax %, Equity Capital+Reserves→
    book value). Takes latest column.
  - `merge_financials(screener, yf)`: Screener wins fundamentals, yfinance wins
    price/shares/mcap/P/E; gaps back-filled from yfinance.
- `src/precedent_db.py`: SQLite `data/precedent_deals.db`, raw-SQL queries:
  `sector_premium_stats` (ROW_NUMBER median + NTILE(4) quartiles),
  `comparable_deals` (CTE size-band bucketing, param-filtered),
  `consideration_mix_trend` (GROUP BY year + HAVING ≥2),
  `premium_vs_multiple` (sector-average CTE join). All return DataFrames.
- `data/seeds/precedent_deals_seed.csv`: 37 real India deals 2019–2025
  (L&T-Mindtree, HDFC merger, Adani-Ambuja/ACC, PVR-INOX, Nirma-Glenmark Life,
  Torrent-JB Chem, JSW Paints-Akzo, etc). **Every row's numbers are marked
  `ILLUSTRATIVE — verify`** with a generic SEBI/NSE/BSE source URL — AR to
  verify/expand against actual letters of offer before publishing.

### Verification results (all pass)
- `python src/precedent_db.py` → 37 rows loaded, all 4 queries non-empty.
- `python src/data_layer.py` → RELIANCE.NS: ₹1,308, mcap ₹17.70 lakh Cr,
  EPS 59.64, P/E 21.9, tax 22.37% — price×shares ties to mcap within 5%.
- Screener CSV fixture (`data/screener_uploads/sample_screener.csv`) loads;
  merge override rules verified (screener fundamentals + yfinance price).

### Decisions made
- `CompanyFinancials` defined in `data_layer.py` (Phase 1 needs it); `deal.py`
  will import it rather than redefine.
- SQLite lacks PERCENTILE_CONT → median via ROW_NUMBER midpoint, p25/p75 via
  NTILE(4) tile maxima; documented in module docstring. p75 is NaN for sectors
  with <4 premium data points — expected, not a bug.
- Self-checks live in `__main__` blocks (no test framework until Phase 2's
  known-deal test).
- Python 3.14.5 local; WeasyPrint decision deferred to Phase 5 (fpdf2 fallback
  already in requirements).

### Pending / next (Phase 2)
- deal.py (DealTerms), sources_uses.py, rbi_compliance.py, sebi_sast.py,
  ppa.py, accretion_dilution.py, sensitivity.py, contribution.py,
  tests/test_known_deal.py with hand-shown arithmetic.
- AR: review seed CSV rows, replace ILLUSTRATIVE numbers with filing-verified
  figures where possible.
