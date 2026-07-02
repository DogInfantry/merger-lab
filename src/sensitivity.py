"""Two-way sensitivity grids on Year-1 accretion %.

methodology:
    Each cell re-runs the full deterministic engine (S&U -> PPA -> A/D)
    with one dataclasses.replace'd DealTerms — no shortcut algebra, so the
    grids can never drift from the engine. Premium axes are expressed vs
    the target's undisturbed price; offer price = price x (1 + premium).
    Grid 1: premium (base +/- 10 pts, 2.5 pt steps) x synergies (0 to 2x
    base in 25% steps). Grid 2: pct_cash (0-100, 10 pt steps) x premium.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from accretion_dilution import run_deal
from data_layer import CompanyFinancials
from deal import DealTerms


def _y1(acquirer, target, terms) -> float:
    return run_deal(acquirer, target, terms).year1_accretion_pct


def premium_x_synergies(
    acquirer: CompanyFinancials, target: CompanyFinancials, terms: DealTerms
) -> pd.DataFrame:
    """Rows: premium %. Columns: synergies (INR Cr). Values: Y1 accretion %."""
    base_premium = terms.premium_over(target.price) * 100
    premiums = np.arange(base_premium - 10, base_premium + 10.01, 2.5)
    synergies = np.linspace(0, 2 * terms.synergies_annual, 9) \
        if terms.synergies_annual else np.linspace(0, 100, 9)

    grid = {}
    for s in synergies:
        col = []
        for p in premiums:
            t = replace(terms, offer_price=target.price * (1 + p / 100),
                        synergies_annual=float(s))
            col.append(round(_y1(acquirer, target, t), 2))
        grid[round(float(s), 0)] = col
    df = pd.DataFrame(grid, index=[round(p, 1) for p in premiums])
    df.index.name = "Premium % \\ Synergies Cr"
    return df


def cash_x_premium(
    acquirer: CompanyFinancials, target: CompanyFinancials, terms: DealTerms
) -> pd.DataFrame:
    """Rows: pct_cash. Columns: premium %. Values: Y1 accretion %."""
    base_premium = terms.premium_over(target.price) * 100
    premiums = np.arange(base_premium - 10, base_premium + 10.01, 2.5)

    grid = {}
    for p in premiums:
        col = []
        for cash in range(0, 101, 10):
            t = replace(terms, offer_price=target.price * (1 + p / 100),
                        pct_cash=float(cash), pct_stock=float(100 - cash))
            col.append(round(_y1(acquirer, target, t), 2))
        grid[round(p, 1)] = col
    df = pd.DataFrame(grid, index=range(0, 101, 10))
    df.index.name = "% Cash \\ Premium %"
    return df
