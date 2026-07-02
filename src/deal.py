"""Deal objects: DealTerms (CompanyFinancials lives in data_layer).

methodology:
    All amounts INR crore, rates as decimals, percentages of consideration
    as 0-100. pct_cash + pct_stock must sum to 100 (of the negotiated
    equity consideration). pct_new_debt_of_cash_portion is the share of
    TOTAL cash needs (cash consideration + open offer + refinance + fees)
    funded by new bank debt; the rest comes off the acquirer's balance
    sheet and forgoes cash_yield_foregone. Default tax = 25.17% India
    corporate rate. synergy_phase_in gives the fraction of run-rate
    synergies realized in years 1-3.
"""

from __future__ import annotations

from dataclasses import dataclass

from data_layer import CompanyFinancials  # noqa: F401  (re-export for Phase 2+ callers)


@dataclass
class DealTerms:
    offer_price: float                      # INR per target share
    pct_cash: float                         # 0-100 of negotiated equity consideration
    pct_stock: float                        # 0-100
    pct_new_debt_of_cash_portion: float     # 0-100 of total cash needs from new bank debt
    debt_interest_rate: float               # decimal, e.g. 0.09
    cash_yield_foregone: float              # decimal yield lost on balance-sheet cash used
    synergies_annual: float                 # INR Cr pre-tax run-rate
    synergy_phase_in: tuple[float, float, float] = (0.5, 0.75, 1.0)
    integration_costs: float = 0.0          # INR Cr pre-tax, Year 1 only
    include_integration_costs: bool = True
    intangible_writeup_pct: float = 0.0     # share of excess-over-book allocated to intangibles
    intangible_life_years: int = 10
    tax_rate: float = 0.2517
    stake_pct: float = 100.0                # negotiated stake in target (before open offer)
    refinance_target_debt: bool = False
    fees_pct: float = 0.015                 # of equity purchase price incl. open offer

    def __post_init__(self) -> None:
        assert abs(self.pct_cash + self.pct_stock - 100.0) < 1e-9, \
            "pct_cash + pct_stock must equal 100"
        assert 0 <= self.pct_new_debt_of_cash_portion <= 100
        assert 0 < self.stake_pct <= 100
        assert self.intangible_life_years > 0

    def premium_over(self, undisturbed_price: float) -> float:
        """Offer premium (decimal) over the target's pre-announcement price."""
        return self.offer_price / undisturbed_price - 1.0
