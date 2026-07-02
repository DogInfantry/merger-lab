"""Financing mix optimizer: maximize Year-1 EPS accretion within RBI guardrails.

methodology:
    Decision variables x = (pct_cash, pct_new_debt_of_cash_portion); pct_stock
    is implied (100 - pct_cash), so the optimizer works in 2 dimensions.
    Objective: maximize Year-1 accretion % from the full deterministic engine
    (no surrogate model — each evaluation is a real S&U -> PPA -> A/D run).
    Constraints (scipy SLSQP inequality form g(x) >= 0):
      - new bank debt <= 75% of acquisition value        (RBI)
      - equity contribution >= 25% of total funding       (RBI)
      - pro-forma consolidated D/E <= 3.0x                (RBI)
      - balance-sheet cash used <= acquirer cash on hand  (practical)
      - new shares issued <= optional dilution ceiling    (user)
    SLSQP is run from a small grid of starting points (the surface is
    piecewise-smooth and near-linear; multistart guards against corner
    traps). A constraint is reported BINDING when its slack at the optimum
    is within tolerance — the binding-constraint narrative feeds the memo
    ("the deal is RBI-debt-cap constrained"). Net-worth and profitability
    checks do not depend on the mix and are reported separately.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.optimize import minimize

from accretion_dilution import run_deal
from data_layer import CompanyFinancials
from deal import DealTerms
from sources_uses import build_sources_uses

_DE_CAP = 3.0
_DEBT_CAP_PCT = 75.0
_MIN_EQUITY_PCT = 25.0


@dataclass
class OptimizerResult:
    pct_cash: float
    pct_stock: float
    pct_new_debt_of_cash_portion: float
    y1_accretion_pct: float
    feasible: bool
    binding_constraints: list[str]
    narrative: str
    optimal_terms: DealTerms


def _mix_metrics(acquirer, target, terms, x, open_offer_cost_cr):
    t = replace(terms, pct_cash=float(x[0]), pct_stock=float(100 - x[0]),
                pct_new_debt_of_cash_portion=float(x[1]))
    su = build_sources_uses(acquirer, target, t, open_offer_cost_cr)
    acq_value = su.equity_purchase_cr + su.open_offer_cost_cr
    debt_pct = su.new_debt_cr / acq_value * 100
    equity_pct = (su.total_sources_cr - su.new_debt_cr) / su.total_sources_cr * 100
    combined_debt = ((acquirer.total_debt_cr or 0.0) + su.new_debt_cr
                     + (0.0 if su.refinance_debt_cr else (target.total_debt_cr or 0.0)))
    combined_equity = (acquirer.book_value_cr or 0.0) + su.new_stock_cr
    de = combined_debt / combined_equity if combined_equity else float("inf")
    return t, su, debt_pct, equity_pct, de


def optimize_financing_mix(
    acquirer: CompanyFinancials,
    target: CompanyFinancials,
    terms: DealTerms,
    open_offer_cost_cr: float = 0.0,
    open_offer_shares_frac: float = 0.0,
    max_new_shares_cr: float | None = None,
) -> OptimizerResult:
    assert acquirer.book_value_cr is not None, "acquirer book value required for D/E constraint"
    acq_cash = acquirer.cash_cr if acquirer.cash_cr is not None else float("inf")

    def objective(x):
        t, *_ = _mix_metrics(acquirer, target, terms, x, open_offer_cost_cr)
        return -run_deal(acquirer, target, t, open_offer_cost_cr,
                         open_offer_shares_frac).year1_accretion_pct

    def slacks(x) -> dict[str, float]:
        _, su, debt_pct, equity_pct, de = _mix_metrics(
            acquirer, target, terms, x, open_offer_cost_cr)
        s = {
            "RBI bank-debt cap (75% of acquisition value)": _DEBT_CAP_PCT - debt_pct,
            "RBI minimum equity contribution (25%)": equity_pct - _MIN_EQUITY_PCT,
            "RBI pro-forma D/E cap (3.0x)": _DE_CAP - de,
            "Acquirer cash on hand": (acq_cash - su.balance_sheet_cash_cr)
                                     / max(acq_cash, 1.0) * 100,
        }
        if max_new_shares_cr is not None:
            s["Dilution ceiling (new shares)"] = (
                (max_new_shares_cr - su.new_shares_cr) / max_new_shares_cr * 100)
        return s

    constraint_names = list(slacks([50.0, 50.0]).keys())
    constraints = [
        {"type": "ineq", "fun": (lambda x, k=name: slacks(x)[k])}
        for name in constraint_names
    ]

    starts = [(50, 50), (100, 100), (0, 0), (100, 0), (25, 75), (75, 25)]
    best = None
    for s0 in starts:
        res = minimize(objective, np.array(s0, dtype=float), method="SLSQP",
                       bounds=[(0, 100), (0, 100)], constraints=constraints,
                       options={"maxiter": 200, "ftol": 1e-9})
        if not res.success:
            continue
        if all(v >= -1e-4 for v in slacks(res.x).values()):
            if best is None or res.fun < best.fun:
                best = res

    if best is None:
        return OptimizerResult(
            pct_cash=float("nan"), pct_stock=float("nan"),
            pct_new_debt_of_cash_portion=float("nan"),
            y1_accretion_pct=float("nan"), feasible=False,
            binding_constraints=[], optimal_terms=terms,
            narrative="No feasible financing mix satisfies the RBI guardrails "
                      "and practical constraints for this deal.",
        )

    x = best.x
    final_slacks = slacks(x)
    # binding = slack within 0.5 units (pct points / normalized %; D/E scaled x100 equiv 0.005x)
    binding = [k for k, v in final_slacks.items()
               if v < (0.05 if "D/E" in k else 0.5)]
    opt_terms, *_ = _mix_metrics(acquirer, target, terms, x, open_offer_cost_cr)
    accretion = -best.fun

    if binding:
        narrative = (f"Optimal mix is constrained: binding constraint(s) — "
                     f"{'; '.join(binding)}. Year-1 accretion at the constrained "
                     f"optimum is {accretion:+.2f}%.")
    else:
        narrative = (f"Optimum is interior — no RBI guardrail binds. The mix is "
                     f"driven purely by relative financing costs; Year-1 accretion "
                     f"{accretion:+.2f}%.")

    return OptimizerResult(
        pct_cash=round(float(x[0]), 1),
        pct_stock=round(float(100 - x[0]), 1),
        pct_new_debt_of_cash_portion=round(float(x[1]), 1),
        y1_accretion_pct=round(accretion, 3),
        feasible=True,
        binding_constraints=binding,
        narrative=narrative,
        optimal_terms=opt_terms,
    )
