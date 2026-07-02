"""Data layer: yfinance fetch + Screener.in CSV fallback.

methodology:
    All monetary values are normalized to INR crore (1 crore = 1e7).
    yfinance is the source for price/shares/market data; Screener.in CSV
    exports win for fundamentals when both are present (merge_financials).
    Effective tax rate = Tax Provision / Pretax Income from the latest
    annual income statement; falls back to 25.17% (India corporate rate:
    22% base + 10% surcharge + 4% cess) when unavailable.
    Missing fields are returned as None and logged — never fabricated.
    yfinance pulls are cached to data/cache/<ticker>.json for 24h.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger("merger_lab.data_layer")

CRORE = 1e7
INDIA_DEFAULT_TAX_RATE = 0.2517
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_TTL_SECONDS = 24 * 3600


@dataclass
class CompanyFinancials:
    """One company's snapshot. Monetary fields in INR crore, shares in crore."""

    ticker: str
    name: Optional[str] = None
    price: Optional[float] = None                # INR per share
    shares_out_cr: Optional[float] = None        # crore shares (diluted where available)
    market_cap_cr: Optional[float] = None
    diluted_eps_ttm: Optional[float] = None      # INR per share
    pe: Optional[float] = None
    net_income_cr: Optional[float] = None        # TTM
    revenue_cr: Optional[float] = None           # TTM
    ebitda_cr: Optional[float] = None            # TTM
    total_debt_cr: Optional[float] = None
    cash_cr: Optional[float] = None
    net_debt_cr: Optional[float] = None
    interest_expense_cr: Optional[float] = None
    book_value_cr: Optional[float] = None        # total equity book value
    tax_rate: float = INDIA_DEFAULT_TAX_RATE
    source: str = "yfinance"
    asof: Optional[str] = None


def _cr(value) -> Optional[float]:
    """Raw INR -> INR crore, passing None through."""
    if value is None:
        return None
    try:
        return float(value) / CRORE
    except (TypeError, ValueError):
        return None


def _stmt_value(stmt: pd.DataFrame, row: str) -> Optional[float]:
    """Latest-column value of a named row in a yfinance statement, else None."""
    try:
        if stmt is None or stmt.empty or row not in stmt.index:
            return None
        series = stmt.loc[row].dropna()
        return float(series.iloc[0]) if not series.empty else None
    except Exception:
        return None


def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker.replace('.', '_')}.json"


def _read_cache(ticker: str) -> Optional[dict]:
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        if time.time() - payload["fetched_at"] > CACHE_TTL_SECONDS:
            return None
        return payload["data"]
    except (json.JSONDecodeError, KeyError):
        return None


def _write_cache(ticker: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(ticker).write_text(
        json.dumps({"fetched_at": time.time(), "data": data}, indent=2)
    )


def fetch_company(ticker: str, use_cache: bool = True) -> CompanyFinancials:
    """Fetch a listed Indian company via yfinance (.NS/.BO suffix expected).

    Values normalized to INR crore. Missing fields stay None with a warning.
    """
    if use_cache:
        cached = _read_cache(ticker)
        if cached is not None:
            return CompanyFinancials(**cached)

    import yfinance as yf

    tk = yf.Ticker(ticker)
    info = tk.info or {}
    income = tk.income_stmt

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    shares = info.get("sharesOutstanding")

    tax_rate = INDIA_DEFAULT_TAX_RATE
    pretax = _stmt_value(income, "Pretax Income")
    tax_prov = _stmt_value(income, "Tax Provision")
    if pretax and tax_prov is not None and pretax > 0:
        computed = tax_prov / pretax
        if 0.0 <= computed <= 0.45:  # discard distorted one-off years
            tax_rate = round(computed, 4)

    interest = _stmt_value(income, "Interest Expense")

    total_debt_cr = _cr(info.get("totalDebt"))
    cash_cr = _cr(info.get("totalCash"))
    net_debt_cr = (
        total_debt_cr - cash_cr
        if total_debt_cr is not None and cash_cr is not None
        else None
    )

    book_value_cr = None
    if info.get("bookValue") is not None and shares:
        book_value_cr = _cr(info["bookValue"] * shares)

    company = CompanyFinancials(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName"),
        price=float(price) if price is not None else None,
        shares_out_cr=_cr(shares),
        market_cap_cr=_cr(info.get("marketCap")),
        diluted_eps_ttm=info.get("trailingEps"),
        pe=info.get("trailingPE"),
        net_income_cr=_cr(info.get("netIncomeToCommon")),
        revenue_cr=_cr(info.get("totalRevenue")),
        ebitda_cr=_cr(info.get("ebitda")),
        total_debt_cr=total_debt_cr,
        cash_cr=cash_cr,
        net_debt_cr=net_debt_cr,
        interest_expense_cr=_cr(interest),
        book_value_cr=book_value_cr,
        tax_rate=tax_rate,
        source="yfinance",
        asof=time.strftime("%Y-%m-%d"),
    )

    for f in fields(company):
        if getattr(company, f.name) is None and f.name not in ("name",):
            log.warning("%s: field '%s' unavailable from yfinance", ticker, f.name)

    _write_cache(ticker, asdict(company))
    return company


# --- Screener.in CSV fallback -------------------------------------------------

# Screener.in row label -> CompanyFinancials field. Values already in INR Cr.
_SCREENER_ROW_MAP = {
    "sales": "revenue_cr",
    "revenue": "revenue_cr",
    "net profit": "net_income_cr",
    "operating profit": "ebitda_cr",
    "borrowings": "total_debt_cr",
    "interest": "interest_expense_cr",
    "eps in rs": "diluted_eps_ttm",
}


def load_screener_csv(path: str | Path, ticker: str = "") -> CompanyFinancials:
    """Parse a Screener.in CSV export (P&L / balance-sheet rows).

    Expects row labels in the first column, periods in subsequent columns;
    the latest (right-most) numeric value is taken. Book value = Equity
    Capital + Reserves when both rows are present. Screener reports in
    INR crore already, so no scaling is applied.
    """
    raw = pd.read_csv(path, header=None, dtype=str)
    company = CompanyFinancials(ticker=ticker, source="screener")

    equity_capital = reserves = None
    for _, row in raw.iterrows():
        label = str(row.iloc[0]).strip().lower().rstrip("+ ").strip()
        values = pd.to_numeric(
            row.iloc[1:].astype(str).str.replace(",", "").str.replace("%", ""),
            errors="coerce",
        ).dropna()
        if values.empty:
            continue
        latest = float(values.iloc[-1])
        if label in _SCREENER_ROW_MAP:
            setattr(company, _SCREENER_ROW_MAP[label], latest)
        elif label == "equity capital":
            equity_capital = latest
        elif label == "reserves":
            reserves = latest
        elif label == "tax %":
            if 0 <= latest <= 45:
                company.tax_rate = round(latest / 100, 4)

    if equity_capital is not None and reserves is not None:
        company.book_value_cr = equity_capital + reserves

    company.asof = time.strftime("%Y-%m-%d")
    return company


def merge_financials(
    screener: CompanyFinancials, market: CompanyFinancials
) -> CompanyFinancials:
    """Screener.in wins for fundamentals; yfinance wins for price/shares/market data."""
    merged = CompanyFinancials(**asdict(screener))
    for field in ("ticker", "name", "price", "shares_out_cr", "market_cap_cr", "pe"):
        setattr(merged, field, getattr(market, field))
    for f in fields(merged):  # fill any remaining gaps from market data
        if getattr(merged, f.name) is None:
            setattr(merged, f.name, getattr(market, f.name))
    if merged.total_debt_cr is not None and merged.cash_cr is not None:
        merged.net_debt_cr = merged.total_debt_cr - merged.cash_cr
    merged.source = "screener+yfinance"
    return merged


if __name__ == "__main__":
    # ponytail: self-check — live fetch, spot-check sanity of RELIANCE.NS
    logging.basicConfig(level=logging.WARNING)
    c = fetch_company("RELIANCE.NS")
    print(c)
    assert c.price and 500 < c.price < 10000, "price out of sane range"
    assert c.market_cap_cr and c.market_cap_cr > 1_000_000, "mcap should be > 10 lakh Cr"
    assert c.shares_out_cr and abs(c.market_cap_cr - c.price * c.shares_out_cr) / c.market_cap_cr < 0.05
    print("data_layer self-check OK")
