"""Deal package: one orchestrator run feeding both the memo and the Excel model.

methodology:
    Runs every analysis module once over a deal and freezes the results in a
    single DealPackage, so the PDF memo and the Excel model can never show
    different numbers. Conventions:
      - SAST acceptance scenarios each get their own Sources & Uses.
      - The headline A/D, RBI and optimizer runs use the ACCEPTANCE
        ASSUMPTION (default 100% — the conservative full-cost view, since
        the acquirer must fund the whole open offer).
      - Sector premium percentile = share of same-sector precedent premiums
        at or below this deal's premium (empirical CDF on the seed DB).
    Recommendation rules (documented, mechanical):
      DECLINE               if RBI fails or P(Y2 accretive) < 40%
      PROCEED W/ CONDITIONS if value bridge negative, mechanical-accretion
                            warning, MPS breach at the chosen acceptance, or
                            P(Y2) < 65%
      PROCEED               otherwise
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from accretion_dilution import ADResult, run_deal
from collar import CollarAnalysis, price_collar
from contribution import build_contribution
from data_layer import CompanyFinancials
from deal import DealTerms
from monte_carlo import MCResult, run_monte_carlo
from optimizer import OptimizerResult, optimize_financing_mix
from rbi_compliance import RBIComplianceReport, check_rbi_compliance
from sebi_sast import SASTReport, evaluate_sast
from sensitivity import cash_x_premium, premium_x_synergies
from sources_uses import SourcesUses, build_sources_uses
from value_bridge import ValueBridgeResult, build_value_bridge


@dataclass
class DealPackage:
    codename: str
    acquirer: CompanyFinancials
    target: CompanyFinancials
    terms: DealTerms
    wacc: float
    acceptance_assumption_pct: float
    strategic_rationale: list[str]
    key_risks: list[str]
    sast: SASTReport
    su_scenarios: dict[float, SourcesUses]      # acceptance % -> S&U
    su: SourcesUses                             # at the acceptance assumption
    open_offer_cost_cr: float
    owned_frac_extra: float                     # open-offer ownership fraction
    rbi: RBIComplianceReport
    ad: ADResult
    contribution: pd.DataFrame
    contribution_flag: str
    grid_premium_synergies: pd.DataFrame
    grid_cash_premium: pd.DataFrame
    optimizer: OptimizerResult
    mc: MCResult
    value_bridge: ValueBridgeResult
    collar: CollarAnalysis | None
    premium_pct: float
    ev_ebitda_offer: float | None
    pe_offer: float | None
    sector_premium_percentile: float | None
    sector_comps: pd.DataFrame | None
    recommendation: str = ""
    recommendation_rationale: str = ""

    def _decide(self) -> None:
        conditions = []
        if not self.rbi.overall_pass:
            failed = ", ".join(c.name for c in self.rbi.binding_or_failed)
            self.recommendation = "DECLINE"
            self.recommendation_rationale = (
                f"RBI acquisition-finance guardrails fail ({failed}); the deal is "
                f"not financeable as structured.")
            return
        if self.mc.p_y2_accretive < 0.40:
            self.recommendation = "DECLINE"
            self.recommendation_rationale = (
                f"Only {self.mc.p_y2_accretive:.0%} probability of Year-2 accretion "
                f"— earnings risk outweighs strategic merit at this price.")
            return
        if self.value_bridge.net_value_created_cr < 0:
            conditions.append("negative value bridge (synergy PV < control premium)")
        if self.value_bridge.mechanical_accretion_warning:
            conditions.append("accretion is mechanical P/E arbitrage")
        scen = next(s for s in self.sast.scenarios
                    if s.acceptance_pct == self.acceptance_assumption_pct) \
            if self.sast.scenarios else None
        if scen and scen.mps_breach:
            conditions.append("MPS breach at the assumed open-offer acceptance")
        if self.mc.p_y2_accretive < 0.65:
            conditions.append(f"P(Y2 accretive) only {self.mc.p_y2_accretive:.0%}")
        if conditions:
            self.recommendation = "PROCEED WITH CONDITIONS"
            self.recommendation_rationale = (
                "RBI-compliant and financeable, but: " + "; ".join(conditions) + ".")
        else:
            self.recommendation = "PROCEED"
            self.recommendation_rationale = (
                f"RBI-compliant, {self.mc.p_y2_accretive:.0%} probability of Year-2 "
                f"accretion and Rs {self.value_bridge.net_value_created_cr:,.0f} Cr "
                f"of net value created for acquirer shareholders.")


def build_deal_package(
    acquirer: CompanyFinancials,
    target: CompanyFinancials,
    terms: DealTerms,
    codename: str = "Project X",
    strategic_rationale: list[str] | None = None,
    key_risks: list[str] | None = None,
    wacc: float = 0.12,
    acceptance_assumption_pct: float = 100.0,
    profitability_track_record: bool = True,
    months_to_close: float = 6.0,
    volatility: float | None = None,
    collar_band: tuple[float, float] = (0.90, 1.10),
    risk_free_rate: float = 0.07,
    precedent_conn=None,
    sector: str | None = None,
) -> DealPackage:
    deal_value = terms.offer_price * target.shares_out_cr * terms.stake_pct / 100
    sast = evaluate_sast(target, terms, deal_value_cr=deal_value)

    su_scenarios: dict[float, SourcesUses] = {}
    if sast.triggered:
        for scen in sast.scenarios:
            su_scenarios[scen.acceptance_pct] = build_sources_uses(
                acquirer, target, terms, open_offer_cost_cr=scen.cost_cr)
        assumed = next(s for s in sast.scenarios
                       if s.acceptance_pct == acceptance_assumption_pct)
        oo_cost = assumed.cost_cr
        oo_frac = (assumed.post_holding_pct - terms.stake_pct) / 100
    else:
        su_scenarios[0.0] = build_sources_uses(acquirer, target, terms)
        oo_cost, oo_frac = 0.0, 0.0
        acceptance_assumption_pct = 0.0

    su = su_scenarios[acceptance_assumption_pct]
    rbi = check_rbi_compliance(acquirer, target, su, profitability_track_record)
    ad = run_deal(acquirer, target, terms, oo_cost, oo_frac)
    contrib, contrib_flag = build_contribution(acquirer, target, su)
    opt = optimize_financing_mix(acquirer, target, terms, oo_cost, oo_frac)
    mc = run_monte_carlo(acquirer, target, terms, oo_cost, oo_frac)
    vb = build_value_bridge(acquirer, target, terms, ad, wacc)

    collar = None
    if terms.pct_stock > 0 and volatility is not None:
        ratio = (terms.pct_stock / 100 * terms.offer_price) / acquirer.price
        collar = price_collar(
            acquirer_price=acquirer.price, exchange_ratio=ratio,
            floor_price=collar_band[0] * acquirer.price,
            cap_price=collar_band[1] * acquirer.price,
            months_to_close=months_to_close, volatility=volatility,
            risk_free_rate=risk_free_rate)

    premium_pct = terms.premium_over(target.price) * 100
    equity_at_offer = terms.offer_price * target.shares_out_cr
    ev_ebitda = ((equity_at_offer + (target.net_debt_cr or 0.0)) / target.ebitda_cr
                 if target.ebitda_cr else None)
    pe = equity_at_offer / target.net_income_cr if target.net_income_cr else None

    percentile, comps = None, None
    if precedent_conn is not None and sector:
        from precedent_db import comparable_deals
        comps = comparable_deals(precedent_conn, sector)
        prem = pd.read_sql_query(
            "SELECT offer_premium_pct FROM deals "
            "WHERE sector = ? AND offer_premium_pct IS NOT NULL",
            precedent_conn, params=(sector,))["offer_premium_pct"]
        if len(prem):
            percentile = float((prem <= premium_pct).mean() * 100)

    pkg = DealPackage(
        codename=codename, acquirer=acquirer, target=target, terms=terms,
        wacc=wacc, acceptance_assumption_pct=acceptance_assumption_pct,
        strategic_rationale=strategic_rationale or [],
        key_risks=key_risks or [], sast=sast, su_scenarios=su_scenarios,
        su=su, open_offer_cost_cr=oo_cost, owned_frac_extra=oo_frac,
        rbi=rbi, ad=ad, contribution=contrib, contribution_flag=contrib_flag,
        grid_premium_synergies=premium_x_synergies(acquirer, target, terms),
        grid_cash_premium=cash_x_premium(acquirer, target, terms),
        optimizer=opt, mc=mc, value_bridge=vb, collar=collar,
        premium_pct=premium_pct, ev_ebitda_offer=ev_ebitda, pe_offer=pe,
        sector_premium_percentile=percentile, sector_comps=comps,
    )
    pkg._decide()
    return pkg
