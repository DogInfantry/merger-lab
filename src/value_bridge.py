"""Value bridge: accretion is not value creation. The senior-banker module.

methodology:
    EPS accretion is mechanical when a high-P/E acquirer buys a low-P/E
    target — it says nothing about value. This module makes that explicit:

    Value creation bridge (INR Cr, acquirer shareholders' perspective):
        PV of synergies = synergies x (1 - t) / WACC
            (perpetuity at user WACC, 0% growth — documented simplification;
             phase-in ramp and integration one-offs are ignored in the PV)
        Control premium paid = (offer - undisturbed price) x target shares
                               actually acquired (negotiated + open offer)
        Net value created  = PV synergies - premium paid

    Mechanical-accretion warning: deal is Year-1 EPS-accretive AND the
    bridge is negative -> "accretion driven by P/E arbitrage, not economics".

    ROIC check: incremental NOPAT / invested capital vs WACC, where
        incremental NOPAT = owned% x target NI + run-rate synergies x (1-t)
        invested capital  = total Uses (equity + open offer + refinance + fees)
"""

from __future__ import annotations

from dataclasses import dataclass

from accretion_dilution import ADResult
from data_layer import CompanyFinancials
from deal import DealTerms


@dataclass
class ValueBridgeResult:
    pv_synergies_cr: float
    premium_paid_cr: float
    net_value_created_cr: float
    mechanical_accretion_warning: bool
    roic_pct: float
    wacc_pct: float
    roic_exceeds_wacc: bool
    narrative: str


def build_value_bridge(
    acquirer: CompanyFinancials,
    target: CompanyFinancials,
    terms: DealTerms,
    ad: ADResult,
    wacc: float,
    undisturbed_price: float | None = None,
) -> ValueBridgeResult:
    assert wacc > 0, "WACC must be positive"
    t = terms.tax_rate
    price0 = undisturbed_price if undisturbed_price is not None else target.price
    assert price0, "target undisturbed price required"

    pv_synergies = terms.synergies_annual * (1 - t) / wacc
    shares_acquired = ad.owned_frac * target.shares_out_cr
    premium_paid = (terms.offer_price - price0) * shares_acquired
    net_value = pv_synergies - premium_paid

    y1_accretive = ad.year1_accretion_pct > 0
    warning = y1_accretive and net_value < 0

    invested = ad.su.total_uses_cr
    inc_nopat = (ad.owned_frac * target.net_income_cr
                 + terms.synergies_annual * (1 - t))
    roic = inc_nopat / invested * 100

    narrative = (
        f"PV of after-tax synergies Rs {pv_synergies:,.0f} Cr vs control premium "
        f"paid Rs {premium_paid:,.0f} Cr -> net value "
        f"{'created' if net_value >= 0 else 'DESTROYED'} Rs {abs(net_value):,.0f} Cr. "
        f"Incremental ROIC {roic:.1f}% vs WACC {wacc * 100:.1f}%."
    )
    if warning:
        narrative += (
            " WARNING: Accretive but value-destructive — EPS accretion is driven "
            "by P/E arbitrage, not economics."
        )

    return ValueBridgeResult(
        pv_synergies_cr=pv_synergies,
        premium_paid_cr=premium_paid,
        net_value_created_cr=net_value,
        mechanical_accretion_warning=warning,
        roic_pct=roic,
        wacc_pct=wacc * 100,
        roic_exceeds_wacc=roic > wacc * 100,
        narrative=narrative,
    )
