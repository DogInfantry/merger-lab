"""Purchase price accounting: intangible write-up, DTL, goodwill, incremental D&A.

methodology:
    Standard simplified PPA on the equity invested in the target (negotiated
    stake + any open offer shares, all at the offer price):
        excess           = equity invested - owned% x target book value
        intangible w/u   = intangible_writeup_pct x excess (floored at 0)
        DTL              = write-up x tax rate (book-tax basis difference)
        goodwill         = excess - write-up + DTL
        incremental D&A  = write-up / intangible_life_years  (straight line)
    Negative excess (bargain purchase) yields zero write-up and negative
    goodwill, reported as-is. PP&E step-up, minority-interest goodwill and
    deal-contingent items are deliberately out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass

from data_layer import CompanyFinancials
from deal import DealTerms


@dataclass
class PPAResult:
    equity_invested_cr: float
    owned_book_value_cr: float
    excess_over_book_cr: float
    intangible_writeup_cr: float
    dtl_cr: float
    goodwill_cr: float
    incremental_da_cr: float          # per year


def run_ppa(
    target: CompanyFinancials,
    terms: DealTerms,
    equity_invested_cr: float,
    owned_frac: float,
) -> PPAResult:
    """PPA on the equity actually invested (negotiated + open offer shares)."""
    assert target.book_value_cr is not None, "target book value required for PPA"
    owned_book = owned_frac * target.book_value_cr
    excess = equity_invested_cr - owned_book
    writeup = max(0.0, terms.intangible_writeup_pct * excess)
    dtl = writeup * terms.tax_rate
    goodwill = excess - writeup + dtl
    return PPAResult(
        equity_invested_cr=equity_invested_cr,
        owned_book_value_cr=owned_book,
        excess_over_book_cr=excess,
        intangible_writeup_cr=writeup,
        dtl_cr=dtl,
        goodwill_cr=goodwill,
        incremental_da_cr=writeup / terms.intangible_life_years,
    )
