"""Phase 3 verification: optimizer constraints, MC point-mass identity,
seed reproducibility, value-bridge sanity law.
Run: python tests/test_quant_layer.py (also pytest-compatible).
Reuses the hand-checked toy deal from test_known_deal.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dataclasses import replace

import numpy as np

from accretion_dilution import run_deal
from monte_carlo import MCConfig, run_monte_carlo
from optimizer import optimize_financing_mix
from sources_uses import build_sources_uses
from test_known_deal import ACQUIRER, TARGET, TERMS
from value_bridge import build_value_bridge


def test_optimizer_respects_constraints():
    # Make debt clearly the cheapest source (7% debt vs 8% foregone yield vs
    # ~8% acquirer earnings yield): unconstrained optimum would be 100% debt,
    # so the RBI 75% cap must bind — and be respected.
    debt_cheap = replace(TERMS, debt_interest_rate=0.07, cash_yield_foregone=0.08)
    res = optimize_financing_mix(ACQUIRER, TARGET, debt_cheap)
    assert res.feasible
    su = build_sources_uses(ACQUIRER, TARGET, res.optimal_terms)
    acq_value = su.equity_purchase_cr
    assert su.new_debt_cr / acq_value * 100 <= 75.0 + 1e-3, "RBI debt cap violated"
    equity_pct = (su.total_sources_cr - su.new_debt_cr) / su.total_sources_cr * 100
    assert equity_pct >= 25.0 - 1e-3, "RBI equity floor violated"
    assert any("debt cap" in b for b in res.binding_constraints), \
        f"debt cap should bind, got {res.binding_constraints}"
    # Optimizer must beat or match the base mix
    assert res.y1_accretion_pct >= run_deal(ACQUIRER, TARGET, debt_cheap).year1_accretion_pct - 1e-6


def test_optimizer_dilution_ceiling():
    # Force stock to be attractive (debt 14%, cash yield 12%) then cap new shares.
    stock_cheap = replace(TERMS, debt_interest_rate=0.14, cash_yield_foregone=0.12)
    res = optimize_financing_mix(ACQUIRER, TARGET, stock_cheap, max_new_shares_cr=3.0)
    assert res.feasible
    su = build_sources_uses(ACQUIRER, TARGET, res.optimal_terms)
    assert su.new_shares_cr <= 3.0 + 1e-6, "dilution ceiling violated"


def test_mc_point_mass_reproduces_engine():
    # Point-mass distributions -> every draw equals the deterministic engine.
    cfg = MCConfig(n_iterations=100, seed=7,
                   synergy_triangular=(1.0, 1.0, 1.0),
                   integration_log_sigma=0.0,
                   delay_probs={0: 1.0})
    mc = run_monte_carlo(ACQUIRER, TARGET, TERMS, config=cfg)
    det = run_deal(ACQUIRER, TARGET, TERMS)
    assert np.allclose(mc.y1_accretion, det.years[0].accretion_pct, atol=1e-9)
    assert np.allclose(mc.y2_accretion, det.years[1].accretion_pct, atol=1e-9)


def test_mc_reproducible_with_seed():
    a = run_monte_carlo(ACQUIRER, TARGET, TERMS)
    b = run_monte_carlo(ACQUIRER, TARGET, TERMS)
    assert np.array_equal(a.y1_accretion, b.y1_accretion)
    assert a.p_y2_accretive == b.p_y2_accretive
    assert 0.0 <= a.p_y2_accretive <= 1.0
    assert a.y2_p5 <= a.y2_p50 <= a.y2_p95
    assert "Probability of accretion by Year 2" in a.memo_line()


def test_value_bridge_sanity_law():
    # SANITY LAW: zero synergies + any positive premium -> negative value creation.
    no_syn = replace(TERMS, synergies_annual=0.0)  # offer 60 vs price 50 = 20% premium
    ad = run_deal(ACQUIRER, TARGET, no_syn)
    vb = build_value_bridge(ACQUIRER, TARGET, no_syn, ad, wacc=0.12)
    assert vb.pv_synergies_cr == 0.0
    # Premium paid = (60 - 50) x 20 Cr shares = 200 Cr
    assert abs(vb.premium_paid_cr - 200.0) < 1e-6
    assert vb.net_value_created_cr < 0


def test_value_bridge_mechanical_accretion_warning():
    # High-P/E acquirer buys low-P/E target all-stock at zero synergies with a
    # premium -> Y1 accretive but value bridge negative -> warning must fire.
    mech = replace(TERMS, pct_cash=0.0, pct_stock=100.0, synergies_annual=0.0,
                   integration_costs=0.0, intangible_writeup_pct=0.0, fees_pct=0.0)
    # Acquirer P/E 12.5 vs target at offer: 1,200/100 = 12.0x -> accretive
    ad = run_deal(ACQUIRER, TARGET, mech)
    assert ad.year1_accretion_pct > 0, "P/E arbitrage deal should be accretive"
    vb = build_value_bridge(ACQUIRER, TARGET, mech, ad, wacc=0.12)
    assert vb.net_value_created_cr < 0
    assert vb.mechanical_accretion_warning
    assert "P/E arbitrage" in vb.narrative


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} quant-layer tests OK")
