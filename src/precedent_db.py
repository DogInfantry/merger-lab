"""Precedent transactions DB: SQLite schema, seed loader, and analysis queries.

methodology:
    Curated India M&A precedents (2019-2026) from public exchange/SEBI
    filings live in data/precedent_deals.db. All analysis queries are raw
    SQL (window functions, CTEs) — deliberately not an ORM, so the SQL is
    auditable. Quartiles use NTILE(4): p25 = max of tile 1, p75 = max of
    tile 3 (SQLite has no PERCENTILE_CONT); median is the average of the
    middle row(s) via ROW_NUMBER. Rows whose notes contain 'ILLUSTRATIVE'
    carry unverified numbers and must be confirmed against the source_url
    filing before external use.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "precedent_deals.db"
SEED_CSV = DATA_DIR / "seeds" / "precedent_deals_seed.csv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    deal_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    announce_date       TEXT NOT NULL,          -- ISO yyyy-mm-dd
    acquirer            TEXT NOT NULL,
    target              TEXT NOT NULL,
    sector              TEXT NOT NULL,
    deal_value_cr       REAL,                   -- INR crore
    consideration_type  TEXT CHECK (consideration_type IN ('cash','stock','mixed')),
    pct_cash            REAL,                   -- 0-100
    offer_premium_pct   REAL,                   -- 1-day premium, %
    ev_ebitda_multiple  REAL,
    pe_multiple         REAL,
    status              TEXT CHECK (status IN ('announced','completed','withdrawn')),
    open_offer          INTEGER NOT NULL DEFAULT 0,  -- bool
    notes               TEXT,
    source_url          TEXT
);
"""


def get_connection(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    return conn


def load_seed(
    conn: sqlite3.Connection, csv_path: str | Path = SEED_CSV, replace: bool = True
) -> int:
    """Load the seed CSV into the deals table. Returns row count loaded."""
    df = pd.read_csv(csv_path)
    if replace:
        conn.execute("DELETE FROM deals")
    df.to_sql("deals", conn, if_exists="append", index=False)
    conn.commit()
    return len(df)


# ---------------------------------------------------------------------------
# Analysis queries — raw SQL on purpose. Read them.
# ---------------------------------------------------------------------------

_SECTOR_PREMIUM_STATS = """
-- Premium distribution by sector: median via ROW_NUMBER midpoint,
-- p25/p75 approximated as the top of NTILE(4) tiles 1 and 3.
WITH ranked AS (
    SELECT
        sector,
        offer_premium_pct,
        ROW_NUMBER() OVER (PARTITION BY sector ORDER BY offer_premium_pct) AS rn,
        COUNT(*)    OVER (PARTITION BY sector)                             AS n,
        NTILE(4)    OVER (PARTITION BY sector ORDER BY offer_premium_pct)  AS quartile
    FROM deals
    WHERE offer_premium_pct IS NOT NULL
)
SELECT
    sector,
    MAX(n)                                                          AS deal_count,
    ROUND(MIN(offer_premium_pct), 1)                                AS min_premium,
    ROUND(MAX(CASE WHEN quartile = 1 THEN offer_premium_pct END), 1) AS p25_premium,
    ROUND(AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2)
              THEN offer_premium_pct END), 1)                       AS median_premium,
    ROUND(MAX(CASE WHEN quartile = 3 THEN offer_premium_pct END), 1) AS p75_premium,
    ROUND(MAX(offer_premium_pct), 1)                                AS max_premium
FROM ranked
GROUP BY sector
ORDER BY deal_count DESC, sector;
"""

_COMPARABLE_DEALS = """
-- Comps pull: bucket deals into size bands, then filter to the requested
-- sector + band. Falls back gracefully: caller passes band = 'ALL' to skip.
WITH sized AS (
    SELECT
        *,
        CASE
            WHEN deal_value_cr IS NULL     THEN 'undisclosed'
            WHEN deal_value_cr <  1000     THEN '< 1,000 Cr'
            WHEN deal_value_cr <  5000     THEN '1,000-5,000 Cr'
            WHEN deal_value_cr <  20000    THEN '5,000-20,000 Cr'
            ELSE                                '> 20,000 Cr'
        END AS size_band
    FROM deals
)
SELECT
    announce_date, acquirer, target, sector, deal_value_cr, size_band,
    consideration_type, offer_premium_pct, ev_ebitda_multiple, pe_multiple,
    status, open_offer, notes, source_url
FROM sized
WHERE sector = :sector
  AND (:size_band = 'ALL' OR size_band = :size_band)
ORDER BY announce_date DESC;
"""

_CONSIDERATION_MIX_TREND = """
-- Cash vs stock mix by announcement year. HAVING drops thin years so the
-- trend line isn't driven by a single deal.
SELECT
    CAST(strftime('%Y', announce_date) AS INTEGER)          AS year,
    COUNT(*)                                                AS deals,
    SUM(CASE WHEN consideration_type = 'cash'  THEN 1 ELSE 0 END) AS cash_deals,
    SUM(CASE WHEN consideration_type = 'stock' THEN 1 ELSE 0 END) AS stock_deals,
    SUM(CASE WHEN consideration_type = 'mixed' THEN 1 ELSE 0 END) AS mixed_deals,
    ROUND(AVG(pct_cash), 1)                                 AS avg_pct_cash
FROM deals
GROUP BY year
HAVING COUNT(*) >= 2
ORDER BY year;
"""

_PREMIUM_VS_MULTIPLE = """
-- Scatter data: each deal's premium vs EV/EBITDA, joined against its
-- sector's average multiple so outliers are readable in context.
WITH sector_avg AS (
    SELECT sector, AVG(ev_ebitda_multiple) AS sector_avg_ev_ebitda
    FROM deals
    WHERE ev_ebitda_multiple IS NOT NULL
    GROUP BY sector
)
SELECT
    d.announce_date,
    d.acquirer,
    d.target,
    d.sector,
    d.offer_premium_pct,
    d.ev_ebitda_multiple,
    ROUND(s.sector_avg_ev_ebitda, 1)                          AS sector_avg_ev_ebitda,
    ROUND(d.ev_ebitda_multiple - s.sector_avg_ev_ebitda, 1)   AS multiple_vs_sector
FROM deals d
JOIN sector_avg s ON s.sector = d.sector
WHERE d.offer_premium_pct IS NOT NULL
  AND d.ev_ebitda_multiple IS NOT NULL
ORDER BY d.offer_premium_pct DESC;
"""


def sector_premium_stats(conn: sqlite3.Connection) -> pd.DataFrame:
    """Median/quartile 1-day offer premium by sector, with deal counts."""
    return pd.read_sql_query(_SECTOR_PREMIUM_STATS, conn)


def comparable_deals(
    conn: sqlite3.Connection, sector: str, size_band: str = "ALL"
) -> pd.DataFrame:
    """Comps in a sector, optionally filtered to a size band.

    size_band: 'ALL', '< 1,000 Cr', '1,000-5,000 Cr', '5,000-20,000 Cr',
    '> 20,000 Cr', or 'undisclosed'.
    """
    return pd.read_sql_query(
        _COMPARABLE_DEALS, conn, params={"sector": sector, "size_band": size_band}
    )


def consideration_mix_trend(conn: sqlite3.Connection) -> pd.DataFrame:
    """Cash vs stock consideration mix by announcement year."""
    return pd.read_sql_query(_CONSIDERATION_MIX_TREND, conn)


def premium_vs_multiple(conn: sqlite3.Connection) -> pd.DataFrame:
    """Premium vs EV/EBITDA scatter data with sector-average context."""
    return pd.read_sql_query(_PREMIUM_VS_MULTIPLE, conn)


if __name__ == "__main__":
    # ponytail: self-check — rebuild DB from seed and run all four queries
    conn = get_connection()
    n = load_seed(conn)
    print(f"loaded {n} seed deals into {DB_PATH.name}")
    for fn, args in [
        (sector_premium_stats, ()),
        (comparable_deals, ("Cement",)),
        (consideration_mix_trend, ()),
        (premium_vs_multiple, ()),
    ]:
        df = fn(conn, *args)
        assert not df.empty, f"{fn.__name__} returned no rows"
        print(f"\n=== {fn.__name__} ===")
        print(df.to_string(index=False))
    print("\nprecedent_db self-check OK")
