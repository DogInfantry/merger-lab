"""RBI acquisition-finance guardrail checks.

methodology:
    Parameters from RBI (Commercial Banks - Credit Facilities) Amendment
    Directions 2026 (amended 13 Feb 2026, effective 1 Apr 2026) — user
    should verify against the master direction before relying on this:
      1. New bank debt <= 75% of acquisition value
         (acquisition value = equity purchase price incl. open offer cost)
      2. Acquirer equity contribution >= 25% of total funding
         (equity contribution = all non-bank-debt sources: stock issued +
         balance-sheet cash)
      3. Pro-forma consolidated D/E <= 3.0x, where
         debt   = acquirer debt + new bank debt + target debt (unless
                  refinanced, in which case it is replaced by new funding)
         equity = acquirer book equity + new stock issued
         (target book equity is eliminated in consolidation against the
         investment; simplification documented)
      4. Acquirer net worth >= Rs 500 Cr (book value)
      5. 3-year profitability track record — user-attested boolean.
"""

from __future__ import annotations

from dataclasses import dataclass

from data_layer import CompanyFinancials
from sources_uses import SourcesUses


@dataclass
class RBICheck:
    name: str
    value: float | bool | None
    threshold: str
    status: str          # 'PASS' / 'FAIL' / 'UNKNOWN'
    explanation: str


@dataclass
class RBIComplianceReport:
    checks: list[RBICheck]

    @property
    def overall_pass(self) -> bool:
        return all(c.status == "PASS" for c in self.checks)

    @property
    def binding_or_failed(self) -> list[RBICheck]:
        return [c for c in self.checks if c.status != "PASS"]


def check_rbi_compliance(
    acquirer: CompanyFinancials,
    target: CompanyFinancials,
    su: SourcesUses,
    profitability_track_record: bool,
) -> RBIComplianceReport:
    checks: list[RBICheck] = []

    acq_value = su.equity_purchase_cr + su.open_offer_cost_cr
    debt_pct = su.new_debt_cr / acq_value * 100 if acq_value else 0.0
    checks.append(RBICheck(
        name="Bank debt <= 75% of acquisition value",
        value=round(debt_pct, 1),
        threshold="<= 75%",
        status="PASS" if debt_pct <= 75.0 else "FAIL",
        explanation=(f"New bank debt Rs {su.new_debt_cr:,.0f} Cr funds "
                     f"{debt_pct:.1f}% of the Rs {acq_value:,.0f} Cr acquisition value."),
    ))

    equity_pct = ((su.total_sources_cr - su.new_debt_cr) / su.total_sources_cr * 100
                  if su.total_sources_cr else 0.0)
    checks.append(RBICheck(
        name="Acquirer equity contribution >= 25%",
        value=round(equity_pct, 1),
        threshold=">= 25%",
        status="PASS" if equity_pct >= 25.0 else "FAIL",
        explanation=(f"Stock + own cash contribute {equity_pct:.1f}% of total "
                     f"funding of Rs {su.total_sources_cr:,.0f} Cr."),
    ))

    if acquirer.book_value_cr is not None:
        combined_debt = ((acquirer.total_debt_cr or 0.0) + su.new_debt_cr
                         + (0.0 if su.refinance_debt_cr else (target.total_debt_cr or 0.0)))
        combined_equity = acquirer.book_value_cr + su.new_stock_cr
        de = combined_debt / combined_equity if combined_equity else float("inf")
        checks.append(RBICheck(
            name="Pro-forma consolidated D/E <= 3.0x",
            value=round(de, 2),
            threshold="<= 3.0x",
            status="PASS" if de <= 3.0 else "FAIL",
            explanation=(f"Combined debt Rs {combined_debt:,.0f} Cr on pro-forma "
                         f"equity Rs {combined_equity:,.0f} Cr = {de:.2f}x."),
        ))
    else:
        checks.append(RBICheck(
            name="Pro-forma consolidated D/E <= 3.0x", value=None,
            threshold="<= 3.0x", status="UNKNOWN",
            explanation="Acquirer book value unavailable — cannot compute pro-forma D/E.",
        ))

    nw = acquirer.book_value_cr
    checks.append(RBICheck(
        name="Acquirer net worth >= Rs 500 Cr",
        value=round(nw, 0) if nw is not None else None,
        threshold=">= Rs 500 Cr",
        status="UNKNOWN" if nw is None else ("PASS" if nw >= 500 else "FAIL"),
        explanation=(f"Acquirer net worth Rs {nw:,.0f} Cr." if nw is not None
                     else "Acquirer book value unavailable."),
    ))

    checks.append(RBICheck(
        name="3-year profitability track record",
        value=profitability_track_record,
        threshold="user-attested",
        status="PASS" if profitability_track_record else "FAIL",
        explanation="Attested by user; verify against 3 years of audited financials.",
    ))

    return RBIComplianceReport(checks=checks)
