"""Sources & Uses. Must balance to the rupee — asserted.

methodology:
    Uses:
        equity purchase   = offer price x target shares x stake%
        open offer cost   = passed in from sebi_sast (cash-settled; SAST
                            open offers are modeled as cash consideration)
        refinance target debt (toggle)
        transaction fees  = fees_pct x (equity purchase + open offer cost)
    Sources:
        new acquirer stock = pct_stock% of the NEGOTIATED equity purchase,
                             issued at the acquirer's current price
        cash needs         = pct_cash% of equity purchase + open offer
                             + refinance + fees
        new bank debt      = pct_new_debt_of_cash_portion% of cash needs
        balance-sheet cash = remaining cash needs
    Balance holds by construction; the assert is a regression tripwire.
"""

from __future__ import annotations

from dataclasses import dataclass

from data_layer import CompanyFinancials
from deal import DealTerms


@dataclass
class SourcesUses:
    # Uses (INR Cr)
    equity_purchase_cr: float
    open_offer_cost_cr: float
    refinance_debt_cr: float
    fees_cr: float
    # Sources (INR Cr)
    new_stock_cr: float
    new_debt_cr: float
    balance_sheet_cash_cr: float
    new_shares_cr: float          # crore shares issued by acquirer

    @property
    def total_uses_cr(self) -> float:
        return (self.equity_purchase_cr + self.open_offer_cost_cr
                + self.refinance_debt_cr + self.fees_cr)

    @property
    def total_sources_cr(self) -> float:
        return self.new_stock_cr + self.new_debt_cr + self.balance_sheet_cash_cr


def build_sources_uses(
    acquirer: CompanyFinancials,
    target: CompanyFinancials,
    terms: DealTerms,
    open_offer_cost_cr: float = 0.0,
) -> SourcesUses:
    assert target.shares_out_cr and acquirer.price, "need target shares and acquirer price"

    equity_purchase = terms.offer_price * target.shares_out_cr * terms.stake_pct / 100
    refinance = (target.total_debt_cr or 0.0) if terms.refinance_target_debt else 0.0
    fees = terms.fees_pct * (equity_purchase + open_offer_cost_cr)

    new_stock = terms.pct_stock / 100 * equity_purchase
    cash_needs = (terms.pct_cash / 100 * equity_purchase
                  + open_offer_cost_cr + refinance + fees)
    new_debt = terms.pct_new_debt_of_cash_portion / 100 * cash_needs
    own_cash = cash_needs - new_debt

    su = SourcesUses(
        equity_purchase_cr=equity_purchase,
        open_offer_cost_cr=open_offer_cost_cr,
        refinance_debt_cr=refinance,
        fees_cr=fees,
        new_stock_cr=new_stock,
        new_debt_cr=new_debt,
        balance_sheet_cash_cr=own_cash,
        new_shares_cr=new_stock / acquirer.price,
    )
    # 1e-6 Cr = 10 rupees of float slack; balance is exact by construction
    assert abs(su.total_sources_cr - su.total_uses_cr) < 1e-6, "S&U does not balance"
    return su
