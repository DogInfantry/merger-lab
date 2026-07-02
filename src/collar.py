"""Exchange-ratio collars for stock/mixed deals, priced with Black-Scholes.

methodology:
    Structures compared:
      - FIXED EXCHANGE RATIO: target holders receive R acquirer shares per
        target share; share count certain, value floats with acquirer price.
      - FLOATING (FIXED VALUE): rupee value per target share is fixed;
        share count floats. Certain value, uncertain dilution.
      - COLLARED FIXED RATIO: ratio R applies while the acquirer price at
        close is within [floor, cap]; outside the band the delivered value
        is trued up (below floor) or capped (above cap).

    Option decomposition (the classic result): a collared fixed-ratio deal
    equals the plain fixed-ratio deal PLUS, per target share,
        + R x European put  on acquirer stock struck at the floor
        - R x European call on acquirer stock struck at the cap
    i.e. target shareholders are LONG the put (downside protection paid for
    by the acquirer) and SHORT the call (they give up upside beyond the cap).
    Collar value per target share = R x (P_bs(floor) - C_bs(cap)).
    Payoff at close per target share = R x clip(S_T, floor, cap).

    Black-Scholes with no dividends (documented simplification; Indian
    large-caps yield 0.3-1.5%, second-order over a 4-9 month deal horizon):
        d1 = (ln(S/K) + (r + sigma^2/2) T) / (sigma sqrt(T)),  d2 = d1 - sigma sqrt(T)
        call = S N(d1) - K e^{-rT} N(d2);  put = K e^{-rT} N(-d2) - S N(-d1)
    N(.) via math.erf (no scipy dependency). sigma = 0 or T = 0 returns
    discounted intrinsic value exactly (sanity-law branch).

    Volatility: annualized realized vol from yfinance daily log returns
    (std x sqrt(252)); sanity-check the level against India VIX manually.
    Risk-free default 7% ~ 10Y G-Sec (CCIL/FIMMDA published, user-updatable).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(s: float, k: float, r: float, sigma: float, t: float) -> float:
    """Black-Scholes European call, no dividends."""
    if t <= 0 or sigma <= 0:
        return max(s - k * math.exp(-r * t), 0.0)
    sq = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (r + sigma**2 / 2) * t) / sq
    d2 = d1 - sq
    return s * _norm_cdf(d1) - k * math.exp(-r * t) * _norm_cdf(d2)


def bs_put(s: float, k: float, r: float, sigma: float, t: float) -> float:
    """Black-Scholes European put, no dividends."""
    if t <= 0 or sigma <= 0:
        return max(k * math.exp(-r * t) - s, 0.0)
    sq = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (r + sigma**2 / 2) * t) / sq
    d2 = d1 - sq
    return k * math.exp(-r * t) * _norm_cdf(-d2) - s * _norm_cdf(-d1)


def annualized_vol(prices: pd.Series) -> float:
    """Annualized realized vol from a daily price series (log returns, sqrt-252)."""
    rets = np.log(prices / prices.shift(1)).dropna()
    return float(rets.std(ddof=1) * math.sqrt(252))


def realized_vol_yf(ticker: str, lookback_days: int = 252) -> float:
    """Realized vol from yfinance daily closes. Sanity-check vs India VIX."""
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period=f"{lookback_days + 10}d")["Close"]
    assert len(hist) > 30, f"insufficient price history for {ticker}"
    return annualized_vol(hist.tail(lookback_days + 1))


@dataclass
class CollarAnalysis:
    exchange_ratio: float
    floor_price: float
    cap_price: float
    months_to_close: float
    volatility: float
    risk_free_rate: float
    put_value: float               # per acquirer share, struck at floor
    call_value: float              # per acquirer share, struck at cap
    collar_value_per_target_share: float   # R x (put - call); +ve = net protection
    payoff: pd.DataFrame           # acquirer price grid -> value per target share
    explanation: str


def price_collar(
    acquirer_price: float,
    exchange_ratio: float,
    floor_price: float,
    cap_price: float,
    months_to_close: float,
    volatility: float,
    risk_free_rate: float = 0.07,
) -> CollarAnalysis:
    """Price the embedded collar optionality in a fixed-ratio stock deal."""
    assert 0 < floor_price < cap_price, "need floor < cap, both positive"
    assert acquirer_price > 0 and exchange_ratio > 0
    t = months_to_close / 12.0

    put = bs_put(acquirer_price, floor_price, risk_free_rate, volatility, t)
    call = bs_call(acquirer_price, cap_price, risk_free_rate, volatility, t)
    collar_value = exchange_ratio * (put - call)

    grid = np.linspace(0.5 * acquirer_price, 1.5 * acquirer_price, 101)
    payoff = pd.DataFrame({
        "acquirer_price": grid,
        "fixed_ratio_value": exchange_ratio * grid,
        "collared_value": exchange_ratio * np.clip(grid, floor_price, cap_price),
    })

    explanation = (
        f"Target shareholders receive {exchange_ratio:.4f} acquirer shares per "
        f"target share, collared between Rs {floor_price:,.0f} and Rs {cap_price:,.0f}. "
        f"They are long a put at the floor (worth Rs {put:.2f}/acquirer share) and "
        f"short a call at the cap (worth Rs {call:.2f}), a net "
        f"{'benefit' if collar_value >= 0 else 'cost'} of Rs {abs(collar_value):.2f} "
        f"per target share at {volatility:.0%} vol over {months_to_close:.0f} months. "
        f"The floor guarantees at least Rs {exchange_ratio * floor_price:,.2f} of value "
        f"per target share if the acquirer's stock falls; in exchange, upside beyond "
        f"Rs {exchange_ratio * cap_price:,.2f} is surrendered to the acquirer. The "
        f"acquirer bears the cost of the downside protection as potential extra "
        f"dilution when its stock trades below the floor at close."
    )

    return CollarAnalysis(
        exchange_ratio=exchange_ratio, floor_price=floor_price,
        cap_price=cap_price, months_to_close=months_to_close,
        volatility=volatility, risk_free_rate=risk_free_rate,
        put_value=put, call_value=call,
        collar_value_per_target_share=collar_value,
        payoff=payoff, explanation=explanation,
    )
