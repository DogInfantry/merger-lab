"""Standalone DCF: intrinsic value of the target, independent of the deal.

methodology:
    Two-stage unlevered free-cash-flow-to-firm (FCFF) DCF, INR crore.
    Accretion/dilution is a RELATIVE test; this is the ABSOLUTE one a CFA
    or an IBBI registered valuer expects. Built only from fields we already
    fetch (revenue, EBITDA, tax, net debt, shares) plus documented, tunable
    driver assumptions — no fabricated line items.

    Stage 1 (explicit, `years`):
        revenue_t   = revenue_{t-1} x (1 + rev_growth)
        EBITDA_t    = revenue_t x ebitda_margin
        D&A_t       = revenue_t x da_pct
        EBIT_t      = EBITDA_t - D&A_t
        NOPAT_t     = EBIT_t x (1 - tax)
        capex_t     = revenue_t x capex_pct
        dNWC_t      = (revenue_t - revenue_{t-1}) x nwc_pct
        FCFF_t      = NOPAT_t + D&A_t - capex_t - dNWC_t
    Terminal value (Gordon growth on the last explicit FCFF):
        TV_N        = FCFF_N x (1 + tg) / (wacc - tg)
    Enterprise value = sum of discounted FCFF_t + discounted TV_N.
    Equity value     = EV - net_debt ; per share = equity / shares.

    Range for the football field: base case plus a bull (wacc-1%, tg+0.5%)
    and bear (wacc+1%, tg-0.5%) re-run. All assumptions are constructor
    arguments (the calibration knobs) so a real analyst can tune them.

    Sanity law (self-check): with rev_growth = 0 and tg = 0 the FCFF is flat,
    so EV must collapse to FCFF / wacc regardless of the explicit horizon.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from data_layer import CompanyFinancials


@dataclass
class DCFResult:
    ev_cr: float
    equity_value_cr: float
    value_per_share: float
    upside_vs_price_pct: float | None
    per_share_low: float
    per_share_high: float
    pv_explicit_cr: float
    pv_terminal_cr: float
    terminal_frac: float               # PV(TV) / EV — how much rides on the terminal
    fcff_by_year_cr: list[float]
    assumptions: dict[str, float] = field(default_factory=dict)
    narrative: str = ""


def _fcff_dcf(
    revenue0: float, ebitda_margin: float, da_pct: float, capex_pct: float,
    nwc_pct: float, tax: float, wacc: float, rev_growth: float,
    terminal_growth: float, years: int,
) -> tuple[float, float, float, list[float]]:
    """Return (pv_explicit, pv_terminal, ev, fcff_list). Bare arithmetic."""
    assert wacc > terminal_growth, "WACC must exceed terminal growth"
    pv_explicit = 0.0
    fcff_list: list[float] = []
    revenue_prev = revenue0
    fcff_n = 0.0
    for t in range(1, years + 1):
        revenue = revenue_prev * (1 + rev_growth)
        ebitda = revenue * ebitda_margin
        da = revenue * da_pct
        ebit = ebitda - da
        nopat = ebit * (1 - tax)
        capex = revenue * capex_pct
        dnwc = (revenue - revenue_prev) * nwc_pct
        fcff = nopat + da - capex - dnwc
        pv_explicit += fcff / (1 + wacc) ** t
        fcff_list.append(fcff)
        revenue_prev = revenue
        fcff_n = fcff
    tv = fcff_n * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = tv / (1 + wacc) ** years
    return pv_explicit, pv_terminal, pv_explicit + pv_terminal, fcff_list


def run_dcf(
    target: CompanyFinancials,
    wacc: float = 0.12,
    rev_growth: float = 0.08,
    terminal_growth: float = 0.04,
    years: int = 5,
    ebitda_margin: float | None = None,
    da_pct: float = 0.04,
    capex_pct: float = 0.05,
    nwc_pct: float = 0.02,
    tax: float | None = None,
) -> DCFResult:
    assert target.revenue_cr and target.revenue_cr > 0, "revenue required for DCF"
    assert target.ebitda_cr is not None, "EBITDA required for DCF"
    assert target.shares_out_cr, "shares required for DCF"
    margin = ebitda_margin if ebitda_margin is not None else target.ebitda_cr / target.revenue_cr
    t = tax if tax is not None else target.tax_rate
    net_debt = target.net_debt_cr or 0.0

    def _run(w: float, tg: float) -> float:
        _, _, ev, _ = _fcff_dcf(
            target.revenue_cr, margin, da_pct, capex_pct, nwc_pct, t,
            w, rev_growth, tg, years)
        return (ev - net_debt) / target.shares_out_cr

    pv_exp, pv_tv, ev, fcff = _fcff_dcf(
        target.revenue_cr, margin, da_pct, capex_pct, nwc_pct, t,
        wacc, rev_growth, terminal_growth, years)
    equity = ev - net_debt
    per_share = equity / target.shares_out_cr
    bear = _run(wacc + 0.01, terminal_growth - 0.005)
    bull = _run(wacc - 0.01, terminal_growth + 0.005)
    low, high = min(bear, bull), max(bear, bull)
    upside = ((per_share / target.price - 1) * 100) if target.price else None

    narrative = (
        f"Two-stage FCFF DCF values {target.name or target.ticker} at "
        f"Rs {per_share:,.0f}/share (equity Rs {equity:,.0f} Cr), a range of "
        f"Rs {low:,.0f}-{high:,.0f} across WACC {(wacc-0.01)*100:.0f}-{(wacc+0.01)*100:.0f}%. "
        f"{pv_tv / ev * 100:.0f}% of value sits in the terminal year"
    )
    if upside is not None:
        narrative += (f"; {'+' if upside >= 0 else ''}{upside:.0f}% vs the "
                      f"Rs {target.price:,.0f} market price.")
    else:
        narrative += "."

    return DCFResult(
        ev_cr=ev, equity_value_cr=equity, value_per_share=per_share,
        upside_vs_price_pct=upside, per_share_low=low, per_share_high=high,
        pv_explicit_cr=pv_exp, pv_terminal_cr=pv_tv, terminal_frac=pv_tv / ev,
        fcff_by_year_cr=fcff,
        assumptions={
            "wacc": wacc, "rev_growth": rev_growth,
            "terminal_growth": terminal_growth, "years": float(years),
            "ebitda_margin": margin, "da_pct": da_pct,
            "capex_pct": capex_pct, "nwc_pct": nwc_pct, "tax": t,
        },
        narrative=narrative,
    )


if __name__ == "__main__":
    # Hand-derived sanity law: flat FCFF (rev_growth=0, tg=0) => EV = FCFF / wacc.
    # revenue 1000, margin 0.25 -> EBITDA 250; D&A 0.04*1000=40; EBIT 210;
    # NOPAT 210*0.75=157.5; capex 0.05*1000=50; dNWC 0 (no growth).
    # FCFF = 157.5 + 40 - 50 - 0 = 147.5 ; EV = 147.5 / 0.12 = 1229.1667.
    # equity = EV - net_debt(100) = 1129.1667 ; per share /20 = 56.4583.
    demo = CompanyFinancials(
        ticker="T.NS", name="DcfCo", price=50.0, shares_out_cr=20.0,
        revenue_cr=1000.0, ebitda_cr=250.0, net_debt_cr=100.0, tax_rate=0.25)
    r = run_dcf(demo, wacc=0.12, rev_growth=0.0, terminal_growth=0.0,
                years=5, da_pct=0.04, capex_pct=0.05, nwc_pct=0.02)
    assert abs(r.ev_cr - 147.5 / 0.12) < 1e-6, r.ev_cr
    assert abs(r.value_per_share - 56.4583333) < 1e-4, r.value_per_share
    # horizon-independence under flat FCFF
    r10 = run_dcf(demo, wacc=0.12, rev_growth=0.0, terminal_growth=0.0, years=10)
    assert abs(r10.ev_cr - r.ev_cr) < 1e-6, (r.ev_cr, r10.ev_cr)
    print("dcf.py self-check OK:", r.narrative)
