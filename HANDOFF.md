# HANDOFF — living state doc

## Current status: Phase 1 COMPLETE (2026-07-02) — awaiting AR review

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
