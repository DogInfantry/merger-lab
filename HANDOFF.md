# HANDOFF — living state doc

## Current status: Phase 2 COMPLETE (2026-07-02) — awaiting AR review

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
