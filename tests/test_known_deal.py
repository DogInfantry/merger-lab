"""Known-deal test — the credibility anchor of the repo.

Every expected value below is derived BY HAND in the comments. If this file
disagrees with the engine, the engine is wrong. Run: python tests/test_known_deal.py
(also pytest-compatible).

TOY DEAL "PROJECT ANCHOR"
  Acquirer A: 100 Cr shares @ Rs 100 (mcap 10,000 Cr), NI 800 Cr -> EPS 8.00,
              book value 4,000 Cr, debt 1,000 Cr, cash 2,000 Cr,
              revenue 8,000 Cr, EBITDA 1,600 Cr.
  Target  T:  20 Cr shares @ Rs 50 (mcap 1,000 Cr), NI 100 Cr -> EPS 5.00,
              book value 500 Cr, debt 200 Cr, cash 100 Cr,
              revenue 1,500 Cr, EBITDA 250 Cr.
  Terms: offer Rs 60 (20% premium), 100% stake, 50% cash / 50% stock,
         60% of cash needs from new debt @ 9%, cash yield foregone 5%,
         synergies 50 Cr phased (0.5, 0.75, 1.0), integration 30 Cr in Y1,
         intangible write-up 40% of excess, 10-yr life, tax 25%,
         fees 1.5%, no target-debt refinance.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dataclasses import replace

from accretion_dilution import run_accretion_dilution, run_deal
from contribution import build_contribution
from data_layer import CompanyFinancials
from deal import DealTerms
from ppa import run_ppa
from rbi_compliance import check_rbi_compliance
from sebi_sast import evaluate_sast
from sources_uses import build_sources_uses

ACQUIRER = CompanyFinancials(
    ticker="ACQ.NS", name="Acquirer A", price=100.0, shares_out_cr=100.0,
    market_cap_cr=10_000.0, net_income_cr=800.0, diluted_eps_ttm=8.0,
    revenue_cr=8_000.0, ebitda_cr=1_600.0, total_debt_cr=1_000.0,
    cash_cr=2_000.0, net_debt_cr=-1_000.0, book_value_cr=4_000.0, tax_rate=0.25,
)
TARGET = CompanyFinancials(
    ticker="TGT.NS", name="Target T", price=50.0, shares_out_cr=20.0,
    market_cap_cr=1_000.0, net_income_cr=100.0, diluted_eps_ttm=5.0,
    revenue_cr=1_500.0, ebitda_cr=250.0, total_debt_cr=200.0,
    cash_cr=100.0, net_debt_cr=100.0, book_value_cr=500.0, tax_rate=0.25,
)
TERMS = DealTerms(
    offer_price=60.0, pct_cash=50.0, pct_stock=50.0,
    pct_new_debt_of_cash_portion=60.0, debt_interest_rate=0.09,
    cash_yield_foregone=0.05, synergies_annual=50.0,
    synergy_phase_in=(0.5, 0.75, 1.0), integration_costs=30.0,
    intangible_writeup_pct=0.40, intangible_life_years=10,
    tax_rate=0.25, stake_pct=100.0, fees_pct=0.015,
)


def approx(actual, expected, tol=0.001):
    """Within 0.1% relative (or 0.001 absolute for near-zero values)."""
    assert abs(actual - expected) <= max(abs(expected) * tol, 1e-3), \
        f"expected {expected}, got {actual}"


def test_sources_uses():
    # Equity purchase = 60 x 20 x 100%                      = 1,200 Cr
    # Fees            = 1.5% x 1,200                        =    18 Cr
    # Total Uses      = 1,200 + 18                          = 1,218 Cr
    # Stock           = 50% x 1,200 = 600 -> 600/100        =     6 Cr new shares
    # Cash needs      = 50% x 1,200 + 18 = 618
    # New debt        = 60% x 618                           = 370.8 Cr
    # Own cash        = 618 - 370.8                         = 247.2 Cr
    su = build_sources_uses(ACQUIRER, TARGET, TERMS)
    approx(su.equity_purchase_cr, 1200.0)
    approx(su.fees_cr, 18.0)
    approx(su.total_uses_cr, 1218.0)
    approx(su.new_stock_cr, 600.0)
    approx(su.new_shares_cr, 6.0)
    approx(su.new_debt_cr, 370.8)
    approx(su.balance_sheet_cash_cr, 247.2)
    approx(su.total_sources_cr, su.total_uses_cr)  # balances to the rupee


def test_ppa():
    # Excess    = 1,200 - 500                 = 700 Cr
    # Write-up  = 40% x 700                   = 280 Cr
    # DTL       = 25% x 280                   =  70 Cr
    # Goodwill  = 700 - 280 + 70              = 490 Cr
    # Inc. D&A  = 280 / 10                    =  28 Cr/yr
    su = build_sources_uses(ACQUIRER, TARGET, TERMS)
    p = run_ppa(TARGET, TERMS, su.equity_purchase_cr, owned_frac=1.0)
    approx(p.excess_over_book_cr, 700.0)
    approx(p.intangible_writeup_cr, 280.0)
    approx(p.dtl_cr, 70.0)
    approx(p.goodwill_cr, 490.0)
    approx(p.incremental_da_cr, 28.0)


def test_accretion_dilution():
    # After-tax factor = 0.75. Standalone EPS = 8.00. PF shares = 106.
    # Interest  = 370.8 x 9% x 0.75  = 25.029
    # Foregone  = 247.2 x 5% x 0.75  =  9.27
    # Inc. D&A  = 28 x 0.75          = 21.0
    # Y1: 800 + 100 + 50x0.5x0.75(=18.75) - 25.029 - 9.27 - 21 - 30x0.75(=22.5)
    #     = 840.951 -> EPS 7.9335 -> 7.9335/8 - 1 = -0.831%
    # Y2: 800 + 100 + 50x0.75x0.75(=28.125) - 25.029 - 9.27 - 21
    #     = 872.826 -> EPS 8.23421 -> +2.928%
    # Y3: 800 + 100 + 50x1.0x0.75(=37.5) - 25.029 - 9.27 - 21
    #     = 882.201 -> EPS 8.32265 -> +4.033%
    r = run_deal(ACQUIRER, TARGET, TERMS)
    approx(r.years[0].combined_ni_cr, 840.951)
    approx(r.years[0].pf_eps, 7.93350)
    approx(r.years[0].accretion_pct, -0.8312, tol=0.001)
    approx(r.years[1].combined_ni_cr, 872.826)
    approx(r.years[1].accretion_pct, 2.9276, tol=0.001)
    approx(r.years[2].combined_ni_cr, 882.201)
    approx(r.years[2].accretion_pct, 4.0331, tol=0.001)

    # Break-even Y1 synergies:
    # NI ex-synergies = 840.951 - 18.75 = 822.201
    # Need NI = 8.00 x 106 = 848 -> S x 0.5 x 0.75 = 25.799 -> S = 68.797 Cr
    approx(r.breakeven_synergies_cr, 68.7973, tol=0.001)
    # Cross-check: running the deal AT break-even synergies gives ~0% Y1 accretion
    r0 = run_deal(ACQUIRER, TARGET,
                  replace(TERMS, synergies_annual=r.breakeven_synergies_cr))
    assert abs(r0.year1_accretion_pct) < 0.001


def test_sanity_law_cash_deal():
    # SANITY LAW: 100% cash, zero premium, no synergies/write-up/fees/one-offs
    # -> accretive iff target earnings yield > after-tax cost of funds.
    # Target yield at Rs 50 = 100/1,000 = 10%.
    base = DealTerms(
        offer_price=50.0, pct_cash=100.0, pct_stock=0.0,
        pct_new_debt_of_cash_portion=100.0, debt_interest_rate=0.09,
        cash_yield_foregone=0.05, synergies_annual=0.0,
        integration_costs=0.0, intangible_writeup_pct=0.0,
        tax_rate=0.25, fees_pct=0.0,
    )
    # 9% debt -> after-tax 6.75% < 10% -> accretive
    assert run_deal(ACQUIRER, TARGET, base).year1_accretion_pct > 0
    # 14% debt -> after-tax 10.5% > 10% -> dilutive
    dear = replace(base, debt_interest_rate=0.14)
    assert run_deal(ACQUIRER, TARGET, dear).year1_accretion_pct < 0


def test_rbi_fails_90pct_debt_deal():
    ninety = replace(TERMS, pct_cash=100.0, pct_stock=0.0,
                     pct_new_debt_of_cash_portion=90.0, fees_pct=0.0)
    su = build_sources_uses(ACQUIRER, TARGET, ninety)
    rep = check_rbi_compliance(ACQUIRER, TARGET, su, profitability_track_record=True)
    debt_check = rep.checks[0]
    # Debt = 90% x 1,200 = 1,080 = 90% of acquisition value -> FAIL
    assert debt_check.status == "FAIL"
    equity_check = rep.checks[1]
    assert equity_check.status == "FAIL"  # only 10% equity contribution
    assert not rep.overall_pass


def test_sast_51pct_stake():
    fifty_one = replace(TERMS, stake_pct=51.0)
    # Deal value = 60 x 20 x 51% = 612 Cr (< 2,000 -> no CCI flag)
    rep = evaluate_sast(TARGET, fifty_one, deal_value_cr=612.0)
    assert rep.triggered, "51% stake must trigger open offer"
    assert not rep.cci_approval_required
    # Open offer = 26% x 20 sh x Rs 60 = 312 Cr
    full = next(s for s in rep.scenarios if s.acceptance_pct == 100.0)
    approx(full.cost_cr, 312.0)
    # Post-offer holding = 51 + 26 = 77% > 75% -> MPS breach
    approx(full.post_holding_pct, 77.0)
    assert full.mps_breach
    none = next(s for s in rep.scenarios if s.acceptance_pct == 0.0)
    assert not none.mps_breach and none.cost_cr == 0.0

    # Open offer cost flows into Uses:
    # Uses = 612 (51% stake) + 312 (open offer) + 1.5% x 924 (=13.86) = 937.86 Cr
    su = build_sources_uses(ACQUIRER, TARGET, fifty_one, open_offer_cost_cr=312.0)
    approx(su.total_uses_cr, 937.86)
    approx(su.total_sources_cr, su.total_uses_cr)


def test_contribution():
    # Hand-computed: Revenue T% = 1,500/9,500 = 15.8%; EBITDA = 250/1,850 = 13.5%;
    # NI = 100/900 = 11.1%; ownership T% = 6/106 = 5.7%.
    su = build_sources_uses(ACQUIRER, TARGET, TERMS)
    df, flag = build_contribution(ACQUIRER, TARGET, su)
    get = lambda m, c: float(df.loc[df["Metric"] == m, c].iloc[0])
    approx(get("Revenue", "Target %"), 15.8, tol=0.01)
    approx(get("EBITDA", "Target %"), 13.5, tol=0.01)
    approx(get("Net income", "Target %"), 11.1, tol=0.01)
    approx(get("Pro-forma ownership", "Target %"), 5.7, tol=0.01)
    # Divergence = 5.7 - 11.1 = -5.4 pts -> within 10 pts, no flag
    assert flag == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} known-deal tests OK")
