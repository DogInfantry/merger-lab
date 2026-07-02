"""Contribution analysis: who contributes what vs who owns what.

methodology:
    For stock/mixed deals, compares acquirer vs target % contribution of
    revenue, EBITDA and net income against the pro-forma ownership split
    (target shareholders' ownership = new shares issued / pro-forma shares;
    cash consideration buys out target holders, so only the stock portion
    creates ownership). Flags when target ownership diverges more than
    10 points from its net-income contribution — the classic "premium
    justification required" exhibit.
"""

from __future__ import annotations

import pandas as pd

from data_layer import CompanyFinancials
from sources_uses import SourcesUses

DIVERGENCE_FLAG_PTS = 10.0


def build_contribution(
    acquirer: CompanyFinancials,
    target: CompanyFinancials,
    su: SourcesUses,
) -> tuple[pd.DataFrame, str]:
    """Returns (exhibit DataFrame, flag narrative — empty string if none)."""
    rows = []
    for metric, attr in (("Revenue", "revenue_cr"), ("EBITDA", "ebitda_cr"),
                         ("Net income", "net_income_cr")):
        a, t = getattr(acquirer, attr), getattr(target, attr)
        if a is None or t is None:
            continue
        total = a + t
        rows.append({"Metric": metric,
                     "Acquirer %": round(a / total * 100, 1),
                     "Target %": round(t / total * 100, 1)})

    pf_shares = acquirer.shares_out_cr + su.new_shares_cr
    target_own = su.new_shares_cr / pf_shares * 100
    rows.append({"Metric": "Pro-forma ownership",
                 "Acquirer %": round(100 - target_own, 1),
                 "Target %": round(target_own, 1)})
    df = pd.DataFrame(rows)

    flag = ""
    ni_row = df[df["Metric"] == "Net income"]
    if not ni_row.empty:
        ni_contrib = float(ni_row["Target %"].iloc[0])
        divergence = target_own - ni_contrib
        if abs(divergence) > DIVERGENCE_FLAG_PTS:
            flag = (
                f"Target shareholders receive {target_own:.0f}% ownership while "
                f"contributing {ni_contrib:.0f}% of combined earnings "
                f"({divergence:+.0f} pts) — premium justification required."
            )
    return df, flag
