"""Merger arbitrage: market-implied probability of deal close.

methodology:
    For an announced cash deal, the target trades between the standalone
    downside price D and the offer O. Treating today's target price P as
    the probability-weighted present value at horizon t (years, expected
    time to close) with risk-free r:
        P x (1+r)^t = p x O + (1-p) x D
    =>  p = (P x (1+r)^t - D) / (O - D)
    Annualized arb spread return IF the deal closes:
        (O / P)^(1/t) - 1
    The implied p is reported raw; values outside [0, 1] are flagged in the
    narrative (they mean the market expects a bump above the offer, or a
    downside estimate that is too high) rather than silently clamped.
    Downside D is the user's estimate of the unaffected price if the deal
    breaks (e.g. pre-announcement price adjusted for market moves).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ArbAnalysis:
    implied_close_probability: float     # 0-1 scale (can exceed bounds; see narrative)
    annualized_return_if_close: float    # decimal
    gross_spread_pct: float
    narrative: str


def implied_close_probability(
    target_price: float,
    offer_price: float,
    downside_price: float,
    months_to_close: float,
    risk_free_rate: float = 0.07,
) -> ArbAnalysis:
    assert offer_price > downside_price, "offer must exceed downside estimate"
    assert target_price > 0 and months_to_close > 0
    t = months_to_close / 12.0

    fv_target = target_price * (1 + risk_free_rate) ** t
    p = (fv_target - downside_price) / (offer_price - downside_price)
    ann_return = (offer_price / target_price) ** (1 / t) - 1
    gross = (offer_price / target_price - 1) * 100

    narrative = (
        f"Target at Rs {target_price:,.2f} vs offer Rs {offer_price:,.2f} "
        f"(gross spread {gross:+.1f}%) with estimated break price Rs "
        f"{downside_price:,.2f} implies a {p:.0%} market-assessed probability of "
        f"close over {months_to_close:.0f} months; the arb earns {ann_return:.1%} "
        f"annualized if the deal completes."
    )
    if p > 1:
        narrative += (" Implied probability exceeds 100% — the market is pricing a "
                      "sweetened offer or the downside estimate is too high.")
    elif p < 0:
        narrative += (" Implied probability is negative — the target trades below "
                      "the estimated break price; check the downside assumption.")

    return ArbAnalysis(
        implied_close_probability=p,
        annualized_return_if_close=ann_return,
        gross_spread_pct=gross,
        narrative=narrative,
    )
