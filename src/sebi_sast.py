"""SEBI (SAST) Regulations 2011 — open offer, MPS, creeping acquisition, CCI flags.

methodology:
    Simplified but directionally correct Takeover Code mechanics:
    - Trigger: acquiring >= 25% voting rights (or control) mandates an open
      offer for a MINIMUM 26% of the target's diluted shares from public
      shareholders (Reg 3(1)/4 read with Reg 7).
    - Open offer cost = 26% x target diluted shares x offer price. FLOOR
      PRICE SIMPLIFICATION: the real floor is the highest of several tests
      (negotiated price, 60-day VWAP, market-price tests); we use the deal
      offer price. This cost is ADDED to Uses under acceptance scenarios —
      an India control deal costs materially more than the negotiated stake.
    - Acceptance scenarios 0% / 50% / 100% -> effective ownership and cost.
    - MPS: post-offer holding > 75% breaches Minimum Public Shareholding
      (SCRR 19A) -> sell-down within 12 months or delisting (needs 90%).
    - Creeping acquisition: between 25% and 75%, up to 5% per FY may be
      bought without an open offer (informational flag).
    - CCI: deal value > Rs 2,000 Cr (2024 deal-value threshold) flags
      "CCI approval required" — threshold flag only, no legal simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from data_layer import CompanyFinancials
from deal import DealTerms

OPEN_OFFER_TRIGGER_PCT = 25.0
MIN_OPEN_OFFER_PCT = 26.0
MPS_LIMIT_PCT = 75.0
DELISTING_THRESHOLD_PCT = 90.0
CCI_DEAL_VALUE_CR = 2000.0
CREEPING_LIMIT_PCT_PER_FY = 5.0


@dataclass
class OpenOfferScenario:
    acceptance_pct: float          # 0 / 50 / 100
    shares_bought_cr: float
    cost_cr: float                 # added to Uses
    post_holding_pct: float
    mps_breach: bool
    narrative: str


@dataclass
class SASTReport:
    stake_pct: float
    triggered: bool
    open_offer_size_pct: float
    floor_price_used: float
    scenarios: list[OpenOfferScenario] = field(default_factory=list)
    creeping_note: str = ""
    cci_approval_required: bool = False
    cci_note: str = ""
    narrative: str = ""


def evaluate_sast(
    target: CompanyFinancials,
    terms: DealTerms,
    deal_value_cr: float,
) -> SASTReport:
    """Takeover Code assessment for a negotiated stake_pct at offer_price."""
    assert target.shares_out_cr, "target shares required"
    triggered = terms.stake_pct >= OPEN_OFFER_TRIGGER_PCT

    report = SASTReport(
        stake_pct=terms.stake_pct,
        triggered=triggered,
        open_offer_size_pct=MIN_OPEN_OFFER_PCT if triggered else 0.0,
        floor_price_used=terms.offer_price,
    )

    if triggered:
        offer_shares = MIN_OPEN_OFFER_PCT / 100 * target.shares_out_cr
        for acceptance in (0.0, 50.0, 100.0):
            bought = offer_shares * acceptance / 100
            cost = bought * terms.offer_price
            post = min(100.0, terms.stake_pct + MIN_OPEN_OFFER_PCT * acceptance / 100)
            mps = post > MPS_LIMIT_PCT
            narrative = (
                f"{acceptance:.0f}% acceptance: buy {bought:,.2f} Cr shares for "
                f"Rs {cost:,.0f} Cr; post-offer holding {post:.1f}%."
            )
            if mps:
                narrative += (
                    f" BREACHES 75% MPS — must sell down within 12 months or pursue "
                    f"delisting (requires {DELISTING_THRESHOLD_PCT:.0f}%)."
                )
            report.scenarios.append(OpenOfferScenario(
                acceptance_pct=acceptance, shares_bought_cr=bought, cost_cr=cost,
                post_holding_pct=post, mps_breach=mps, narrative=narrative,
            ))
        report.narrative = (
            f"Acquiring {terms.stake_pct:.0f}% crosses the 25% threshold -> mandatory "
            f"open offer for {MIN_OPEN_OFFER_PCT:.0f}% of the target at the floor price "
            f"(modeled at the Rs {terms.offer_price:,.0f} offer price; real floor is the "
            f"highest-of tests incl. 60-day VWAP)."
        )
    else:
        report.narrative = (
            f"Acquiring {terms.stake_pct:.0f}% stays below the 25% open-offer "
            f"threshold — no mandatory open offer."
        )

    if OPEN_OFFER_TRIGGER_PCT <= terms.stake_pct < MPS_LIMIT_PCT:
        report.creeping_note = (
            f"Between 25% and 75%, up to {CREEPING_LIMIT_PCT_PER_FY:.0f}% per FY may be "
            f"acquired without triggering a fresh open offer (creeping acquisition route)."
        )

    if deal_value_cr > CCI_DEAL_VALUE_CR:
        report.cci_approval_required = True
        report.cci_note = (
            f"Deal value Rs {deal_value_cr:,.0f} Cr exceeds the Rs 2,000 Cr deal-value "
            f"threshold (2024 amendment) — CCI approval required; expect ~150-210 days "
            f"outer timeline, Green Channel possible if no overlaps."
        )
    return report
