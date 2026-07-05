"""Valuation-depth integration test: DCF + trading comps + football-field wiring.

Module-level arithmetic is hand-checked in src/dcf.py and src/trading_comps.py
self-checks; this asserts the orchestrator wires them into DealPackage and that
the football-field ranges come out consistent. Run: python tests/test_valuation.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_layer import CompanyFinancials
from deal import DealTerms
from deal_package import build_deal_package

ACQ = CompanyFinancials(
    ticker="ACQ.NS", name="Acquirer A", price=100.0, shares_out_cr=100.0,
    market_cap_cr=10_000.0, net_income_cr=800.0, diluted_eps_ttm=8.0,
    revenue_cr=8_000.0, ebitda_cr=1_600.0, total_debt_cr=1_000.0,
    cash_cr=2_000.0, net_debt_cr=-1_000.0, book_value_cr=4_000.0, tax_rate=0.25)
TGT = CompanyFinancials(
    ticker="TGT.NS", name="Target T", price=50.0, shares_out_cr=20.0,
    market_cap_cr=1_000.0, net_income_cr=100.0, diluted_eps_ttm=5.0,
    revenue_cr=1_500.0, ebitda_cr=250.0, total_debt_cr=200.0,
    cash_cr=100.0, net_debt_cr=100.0, book_value_cr=500.0, tax_rate=0.25)
TERMS = DealTerms(
    offer_price=60.0, pct_cash=50.0, pct_stock=50.0,
    pct_new_debt_of_cash_portion=60.0, debt_interest_rate=0.09,
    cash_yield_foregone=0.05, synergies_annual=50.0,
    synergy_phase_in=(0.5, 0.75, 1.0), integration_costs=30.0,
    intangible_writeup_pct=0.40, intangible_life_years=10,
    tax_rate=0.25, stake_pct=100.0, fees_pct=0.015)
PEERS = [
    CompanyFinancials(ticker="P1.NS", name="Peer 1", market_cap_cr=1_200.0,
                      net_debt_cr=150.0, ebitda_cr=260.0, revenue_cr=1_600.0,
                      net_income_cr=110.0),
    CompanyFinancials(ticker="P2.NS", name="Peer 2", market_cap_cr=900.0,
                      net_debt_cr=80.0, ebitda_cr=230.0, revenue_cr=1_400.0,
                      net_income_cr=95.0),
    CompanyFinancials(ticker="P3.NS", name="Peer 3", market_cap_cr=1_050.0,
                      net_debt_cr=120.0, ebitda_cr=245.0, revenue_cr=1_500.0,
                      net_income_cr=102.0),
]

passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL {name}"
    passed += 1
    print(f"PASS {name}")


def test_dcf_wired():
    pkg = build_deal_package(ACQ, TGT, TERMS, codename="Project Value")
    check("dcf_present", pkg.dcf is not None)
    check("dcf_positive_per_share", pkg.dcf.value_per_share > 0)
    # DCF-only football field (no peers passed)
    check("one_valuation_bar", len(pkg.valuation_ranges) == 1)
    check("comps_absent_without_peers", pkg.trading_comps is None)


def test_comps_and_football_field():
    pkg = build_deal_package(ACQ, TGT, TERMS, codename="Project Value", peers=PEERS)
    check("comps_present", pkg.trading_comps is not None)
    check("comps_value_positive", pkg.trading_comps.value_per_share > 0)
    check("comps_three_peers", pkg.trading_comps.n_peers == 3)
    check("two_valuation_bars", len(pkg.valuation_ranges) == 2)
    for row in pkg.valuation_ranges:
        check(f"range_ordered_{row['method']}", row["low"] <= row["mid"] <= row["high"])


if __name__ == "__main__":
    test_dcf_wired()
    test_comps_and_football_field()
    print(f"\nall {passed} valuation tests OK")
