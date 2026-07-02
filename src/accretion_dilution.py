"""Accretion/dilution engine: Year 1-3 pro-forma EPS vs standalone acquirer.

methodology:
    Combined net income (year y, INR Cr):
        acquirer NI
      + owned% x target NI                       (economic consolidation of the
                                                  stake actually owned; minority
                                                  interest handled implicitly)
      + synergies x phase_in[y] x (1 - t)
      - new debt x rate x (1 - t)                (new interest expense)
      - balance-sheet cash used x yield x (1 - t) (foregone cash income)
      - incremental D&A x (1 - t)                (from PPA intangible write-up)
      - integration costs x (1 - t)              (Year 1 only, toggle)
    Pro-forma shares = acquirer shares + new shares issued.
    Accretion% = pro-forma EPS / standalone acquirer EPS - 1. Standalone EPS
    is held flat over Y1-3 (no standalone growth modeled — documented
    simplification; the comparison isolates deal effects).

    Break-even synergies (Year 1) solve the linear equation
        (NI_ex_synergies + S x phase_1 x (1-t)) / PF shares = standalone EPS
    =>  S = (standalone EPS x PF shares - NI_ex_synergies) / (phase_1 x (1-t))

    Rule-of-thumb cross-check: a deal tends to be accretive when the target
    earnings yield at the offer (owned NI / equity invested) exceeds the
    blended after-tax cost of financing (debt rate, foregone cash yield,
    acquirer earnings yield for stock). The heuristic ignores synergies,
    write-up D&A and one-offs, so a disagreement with the engine is flagged
    with that caveat rather than treated as an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from data_layer import CompanyFinancials
from deal import DealTerms
from ppa import PPAResult, run_ppa
from sources_uses import SourcesUses, build_sources_uses


@dataclass
class YearResult:
    year: int
    combined_ni_cr: float
    pf_shares_cr: float
    pf_eps: float
    standalone_eps: float
    accretion_pct: float           # +accretive / -dilutive


@dataclass
class ADResult:
    years: list[YearResult]
    breakeven_synergies_cr: float
    heuristic_accretive: bool
    heuristic_note: str
    su: SourcesUses = None
    ppa: PPAResult = None
    owned_frac: float = 1.0

    @property
    def year1_accretion_pct(self) -> float:
        return self.years[0].accretion_pct


def run_accretion_dilution(
    acquirer: CompanyFinancials,
    target: CompanyFinancials,
    terms: DealTerms,
    su: SourcesUses,
    ppa: PPAResult,
    owned_frac: float,
) -> ADResult:
    for c, f_ in ((acquirer, "net_income_cr"), (acquirer, "shares_out_cr"),
                  (target, "net_income_cr")):
        assert getattr(c, f_) is not None, f"{c.ticker}: {f_} required"

    t = terms.tax_rate
    at = 1 - t
    standalone_eps = acquirer.net_income_cr / acquirer.shares_out_cr
    pf_shares = acquirer.shares_out_cr + su.new_shares_cr

    interest = su.new_debt_cr * terms.debt_interest_rate * at
    foregone = su.balance_sheet_cash_cr * terms.cash_yield_foregone * at
    inc_da = ppa.incremental_da_cr * at
    base_ni = (acquirer.net_income_cr + owned_frac * target.net_income_cr
               - interest - foregone - inc_da)

    years: list[YearResult] = []
    for y in (1, 2, 3):
        ni = base_ni + terms.synergies_annual * terms.synergy_phase_in[y - 1] * at
        if y == 1 and terms.include_integration_costs:
            ni -= terms.integration_costs * at
        eps = ni / pf_shares
        years.append(YearResult(
            year=y, combined_ni_cr=ni, pf_shares_cr=pf_shares, pf_eps=eps,
            standalone_eps=standalone_eps,
            accretion_pct=(eps / standalone_eps - 1) * 100,
        ))

    ni_y1_ex_syn = years[0].combined_ni_cr - \
        terms.synergies_annual * terms.synergy_phase_in[0] * at
    breakeven = ((standalone_eps * pf_shares - ni_y1_ex_syn)
                 / (terms.synergy_phase_in[0] * at))

    # Rule-of-thumb cross-check
    equity_invested = su.equity_purchase_cr + su.open_offer_cost_cr
    target_yield = owned_frac * target.net_income_cr / equity_invested
    acq_earnings_yield = standalone_eps / acquirer.price if acquirer.price else 0.0
    total_funding = su.total_sources_cr
    blended_cost = (su.new_debt_cr * terms.debt_interest_rate * at
                    + su.balance_sheet_cash_cr * terms.cash_yield_foregone * at
                    + su.new_stock_cr * acq_earnings_yield) / total_funding
    heuristic_accretive = target_yield > blended_cost
    agrees = heuristic_accretive == (years[0].accretion_pct > 0)
    note = (
        f"Target earnings yield at offer {target_yield:.1%} vs blended after-tax "
        f"financing cost {blended_cost:.1%} -> heuristic says "
        f"{'ACCRETIVE' if heuristic_accretive else 'DILUTIVE'}; engine Year-1 says "
        f"{'ACCRETIVE' if years[0].accretion_pct > 0 else 'DILUTIVE'}."
    )
    if not agrees:
        note += (" DISAGREEMENT — reconciling items: synergies, intangible write-up "
                 "D&A, integration one-offs (heuristic ignores all three).")

    return ADResult(years=years, breakeven_synergies_cr=breakeven,
                    heuristic_accretive=heuristic_accretive, heuristic_note=note,
                    su=su, ppa=ppa, owned_frac=owned_frac)


def run_deal(
    acquirer: CompanyFinancials,
    target: CompanyFinancials,
    terms: DealTerms,
    open_offer_cost_cr: float = 0.0,
    open_offer_shares_frac: float = 0.0,   # extra ownership fraction bought via open offer
) -> ADResult:
    """Convenience wrapper: S&U -> PPA -> accretion/dilution in one call."""
    su = build_sources_uses(acquirer, target, terms, open_offer_cost_cr)
    owned_frac = min(1.0, terms.stake_pct / 100 + open_offer_shares_frac)
    ppa_res = run_ppa(target, terms,
                      equity_invested_cr=su.equity_purchase_cr + su.open_offer_cost_cr,
                      owned_frac=owned_frac)
    return run_accretion_dilution(acquirer, target, terms, su, ppa_res, owned_frac)
