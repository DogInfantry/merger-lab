"""Data-layer unit tests (offline): statement-currency FX inference.
Run: python tests/test_data_layer.py (also pytest-compatible).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_layer import _statement_fx


def test_same_currency_no_scaling():
    assert _statement_fx({"financialCurrency": "INR", "currency": "INR"}) == 1.0
    assert _statement_fx({}) == 1.0


def test_usd_filer_infers_fx():
    # Infosys-style: EPS Rs 64, 415 Cr sh -> NI Rs 26,560 Cr; Yahoo NI $3.1bn.
    # Implied factor = 64 x 4.15e9 / 3.1e9 = 85.68 ~ USDINR.
    info = {"financialCurrency": "USD", "currency": "INR",
            "trailingEps": 64.0, "sharesOutstanding": 4.15e9,
            "netIncomeToCommon": 3.1e9}
    fx = _statement_fx(info)
    assert abs(fx - 64.0 * 4.15e9 / 3.1e9) < 1e-9
    assert 80 < fx < 90


def test_unplausible_factor_left_unscaled():
    # Mismatched currencies but implied factor outside FX band -> 1.0 + warning
    info = {"financialCurrency": "USD", "currency": "INR",
            "trailingEps": 64.0, "sharesOutstanding": 4.15e9,
            "netIncomeToCommon": 2.66e11}   # implied ~1.0 -> not plausible FX
    assert _statement_fx(info) == 1.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} data-layer tests OK")
