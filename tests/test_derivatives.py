"""Phase 4 verification: BS textbook hand-check, zero-vol intrinsic sanity,
put-call parity, collar payoff identity, merger-arb laws.
Run: python tests/test_derivatives.py (also pytest-compatible).
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import pandas as pd

from collar import annualized_vol, bs_call, bs_put, price_collar
from merger_arb import implied_close_probability


def test_bs_textbook_example():
    # Hull-style hand check: S=100, K=100, r=5%, sigma=20%, T=1yr
    #   d1 = (ln(1) + (0.05 + 0.02) x 1) / 0.2 = 0.35;  d2 = 0.15
    #   N(0.35) = 0.63683, N(0.15) = 0.55962
    #   call = 100 x 0.63683 - 100 x e^-0.05 x 0.55962 = 10.4506
    #   put  = call - S + K e^-rT = 10.4506 - 100 + 95.1229 = 5.5735
    assert abs(bs_call(100, 100, 0.05, 0.20, 1.0) - 10.4506) < 0.001
    assert abs(bs_put(100, 100, 0.05, 0.20, 1.0) - 5.5735) < 0.001


def test_put_call_parity():
    # call - put = S - K e^{-rT} must hold for any inputs
    for s, k, r, sig, t in [(120, 100, 0.07, 0.3, 0.5), (80, 100, 0.02, 0.15, 2.0),
                            (100, 90, 0.0, 0.5, 0.25)]:
        lhs = bs_call(s, k, r, sig, t) - bs_put(s, k, r, sig, t)
        rhs = s - k * math.exp(-r * t)
        assert abs(lhs - rhs) < 1e-9, f"parity broken at {(s, k, r, sig, t)}"


def test_zero_vol_intrinsic_only():
    # SANITY LAW: zero vol -> discounted intrinsic value only.
    assert abs(bs_call(110, 100, 0.0, 0.0, 1.0) - 10.0) < 1e-12
    assert bs_call(90, 100, 0.0, 0.0, 1.0) == 0.0
    assert abs(bs_put(90, 100, 0.0, 0.0, 1.0) - 10.0) < 1e-12
    assert bs_put(110, 100, 0.0, 0.0, 1.0) == 0.0
    # Zero-vol collar with spot inside [floor, cap] and r=0 -> zero option value
    c = price_collar(acquirer_price=100, exchange_ratio=0.5, floor_price=90,
                     cap_price=110, months_to_close=6, volatility=0.0,
                     risk_free_rate=0.0)
    assert c.put_value == 0.0 and c.call_value == 0.0
    assert c.collar_value_per_target_share == 0.0


def test_collar_decomposition_and_payoff():
    c = price_collar(acquirer_price=100, exchange_ratio=0.5, floor_price=90,
                     cap_price=110, months_to_close=6, volatility=0.30,
                     risk_free_rate=0.07)
    # Decomposition: collar value = R x (put(floor) - call(cap))
    assert abs(c.collar_value_per_target_share
               - 0.5 * (c.put_value - c.call_value)) < 1e-12
    assert c.put_value > 0 and c.call_value > 0
    # Payoff identity at close: collared value = R x clip(S, floor, cap)
    expected = 0.5 * np.clip(c.payoff["acquirer_price"], 90, 110)
    assert np.allclose(c.payoff["collared_value"], expected)
    # Below floor the target is protected: collared > plain fixed-ratio value
    low = c.payoff[c.payoff["acquirer_price"] < 90]
    assert (low["collared_value"] > low["fixed_ratio_value"]).all()
    assert "long a put" in c.explanation


def test_annualized_vol():
    # Constant prices -> zero vol
    assert annualized_vol(pd.Series([100.0] * 50)) == 0.0
    # Alternating +1%/-1% daily log-returns -> std = 1% x sqrt(252) ~ 15.9%
    prices = pd.Series(100 * np.exp(np.cumsum([0.01, -0.01] * 126)))
    v = annualized_vol(prices)
    assert abs(v - 0.01 * math.sqrt(252)) < 0.002


def test_arb_offer_equals_price():
    # SANITY LAW: target trades AT the offer -> implied close probability
    # ~100% net of carry. With r = 0 it is exactly 100%.
    a = implied_close_probability(target_price=100, offer_price=100,
                                  downside_price=80, months_to_close=6,
                                  risk_free_rate=0.0)
    assert abs(a.implied_close_probability - 1.0) < 1e-12
    # With positive carry it sits above 1 by carry x P/(O-D) and gets flagged:
    # p = 1 + (100 x 1.07^0.5 - 100)/20 = 1.172
    b = implied_close_probability(100, 100, 80, 6, risk_free_rate=0.07)
    assert abs(b.implied_close_probability
               - (1 + (100 * 1.07**0.5 - 100) / 20)) < 1e-12
    assert "sweetened" in b.narrative


def test_arb_hand_example():
    # Hand check: P=95, O=100, D=80, t=6m, r=0:
    #   p = (95 - 80) / (100 - 80) = 0.75
    #   annualized if close = (100/95)^2 - 1 = 10.803%
    a = implied_close_probability(95, 100, 80, 6, risk_free_rate=0.0)
    assert abs(a.implied_close_probability - 0.75) < 1e-12
    assert abs(a.annualized_return_if_close - ((100 / 95) ** 2 - 1)) < 1e-12
    assert abs(a.gross_spread_pct - 5.2632) < 0.001


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} derivatives tests OK")
