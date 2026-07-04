"""Trading comps: value the target off listed-peer multiples.

methodology:
    The precedent-DB gives us TRANSACTION comps; this gives the other half a
    CFA expects — TRADING comps (where the peers trade today), INR crore.

    For each peer:
        EV        = market_cap + net_debt
        EV/EBITDA = EV / EBITDA ; EV/Sales = EV / revenue ; P/E = mcap / NI
    Take the MEDIAN of each multiple across peers (robust to one outlier;
    non-positive / missing multiples are dropped, never imputed).

    Imply the target's equity value per share from each median multiple:
        via EV/EBITDA: EV = m x target.EBITDA ; equity = EV - net_debt
        via EV/Sales : EV = m x target.revenue; equity = EV - net_debt
        via P/E      : equity = m x target.NI
        per share    = equity / shares
    Central estimate = median of the available per-share implications;
    low/high = their min/max (feeds the football field).

    Peer sets (SECTOR_PEERS) are hand-curated lists of PUBLIC tickers — the
    financials are always fetched live, never fabricated. `fetch_sector_peers`
    takes the fetch function by injection so this module stays offline/testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

import pandas as pd

from data_layer import CompanyFinancials

# Hand-curated public peer universes (NSE tickers). Financials fetched live.
SECTOR_PEERS: dict[str, list[str]] = {
    "IT Services": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTIM.NS"],
    "Cement": ["ULTRACEMCO.NS", "SHREECEM.NS", "AMBUJACEM.NS", "ACC.NS", "DALBHARAT.NS", "JKCEMENT.NS"],
    "Metals & Mining": ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "JINDALSTEL.NS", "SAIL.NS", "NMDC.NS"],
    "Pharmaceuticals": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "LUPIN.NS", "AUROPHARMA.NS"],
    "Banks": ["HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS", "SBIN.NS", "INDUSINDBK.NS"],
    "FMCG": ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS", "DABUR.NS", "MARICO.NS"],
    "Automobiles": ["MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS", "HEROMOTOCO.NS"],
}


@dataclass
class TradingCompsResult:
    median_ev_ebitda: float | None
    median_ev_sales: float | None
    median_pe: float | None
    implied_ps_ev_ebitda: float | None
    implied_ps_ev_sales: float | None
    implied_ps_pe: float | None
    value_per_share: float | None      # median of available implications
    per_share_low: float | None
    per_share_high: float | None
    peer_table: pd.DataFrame           # one row per peer, multiples
    n_peers: int
    narrative: str = ""


def _ev(c: CompanyFinancials) -> float | None:
    mcap = c.market_cap_cr
    if mcap is None and c.price and c.shares_out_cr:
        mcap = c.price * c.shares_out_cr
    if mcap is None:
        return None
    return mcap + (c.net_debt_cr or 0.0)


def _pos(x: float | None) -> float | None:
    """Keep strictly-positive finite multiples, drop everything else."""
    return x if (x is not None and x == x and x > 0) else None


def compute_trading_comps(
    target: CompanyFinancials, peers: list[CompanyFinancials]
) -> TradingCompsResult:
    rows, evs, sales, pes = [], [], [], []
    for p in peers:
        ev = _ev(p)
        ev_ebitda = _pos(ev / p.ebitda_cr) if ev and p.ebitda_cr else None
        ev_sales = _pos(ev / p.revenue_cr) if ev and p.revenue_cr else None
        mcap = p.market_cap_cr or (p.price * p.shares_out_cr if p.price and p.shares_out_cr else None)
        pe = _pos(mcap / p.net_income_cr) if mcap and p.net_income_cr else None
        rows.append({"peer": p.name or p.ticker, "ev_ebitda": ev_ebitda,
                     "ev_sales": ev_sales, "pe": pe})
        if ev_ebitda: evs.append(ev_ebitda)
        if ev_sales: sales.append(ev_sales)
        if pe: pes.append(pe)

    m_ev_ebitda = median(evs) if evs else None
    m_ev_sales = median(sales) if sales else None
    m_pe = median(pes) if pes else None
    net_debt = target.net_debt_cr or 0.0
    sh = target.shares_out_cr

    def _ps(equity: float | None) -> float | None:
        return equity / sh if (equity is not None and sh) else None

    ps_ee = _ps(m_ev_ebitda * target.ebitda_cr - net_debt) if m_ev_ebitda and target.ebitda_cr else None
    ps_es = _ps(m_ev_sales * target.revenue_cr - net_debt) if m_ev_sales and target.revenue_cr else None
    ps_pe = _ps(m_pe * target.net_income_cr) if m_pe and target.net_income_cr else None

    implications = [x for x in (ps_ee, ps_es, ps_pe) if x is not None]
    central = median(implications) if implications else None
    low = min(implications) if implications else None
    high = max(implications) if implications else None

    if central is not None:
        narrative = (
            f"Peer trading comps (n={len(rows)}) imply Rs {central:,.0f}/share "
            f"for {target.name or target.ticker} (range Rs {low:,.0f}-{high:,.0f}) at "
            f"median EV/EBITDA {m_ev_ebitda:.1f}x"
            + (f", P/E {m_pe:.1f}x." if m_pe else ".")
        )
    else:
        narrative = f"Insufficient peer data to build trading comps (n={len(rows)})."

    return TradingCompsResult(
        median_ev_ebitda=m_ev_ebitda, median_ev_sales=m_ev_sales, median_pe=m_pe,
        implied_ps_ev_ebitda=ps_ee, implied_ps_ev_sales=ps_es, implied_ps_pe=ps_pe,
        value_per_share=central, per_share_low=low, per_share_high=high,
        peer_table=pd.DataFrame(rows), n_peers=len(rows), narrative=narrative,
    )


def fetch_sector_peers(sector, fetch_fn, exclude=()):
    """Fetch live financials for a sector's peer universe via injected fetch_fn.

    fetch_fn(ticker) -> CompanyFinancials | None. Peers whose ticker is in
    `exclude` (e.g. the acquirer/target themselves) are skipped. Returns [] for
    an unknown sector so the caller can degrade gracefully.
    """
    exclude = {t.upper() for t in exclude}
    out = []
    for tk in SECTOR_PEERS.get(sector, []):
        if tk.upper() in exclude:
            continue
        try:
            c = fetch_fn(tk)
        except Exception:
            c = None
        if c is not None:
            out.append(c)
    return out


if __name__ == "__main__":
    # Hand check: 3 peers all at EV/EBITDA 8x, EV/Sales 2x, P/E 20x.
    #   peer mcap 1000, net_debt 0 -> EV 1000; EBITDA 125 -> 8x; revenue 500 -> 2x;
    #   NI 50 -> P/E 20x.  target: EBITDA 250, revenue 1000, NI 100, net_debt 100, 20 sh.
    #   via EV/EBITDA: EV = 8*250 = 2000; equity 1900; /20 = 95.
    #   via EV/Sales : EV = 2*1000 = 2000; equity 1900; /20 = 95.
    #   via P/E      : equity = 20*100 = 2000; /20 = 100.
    #   central = median(95, 95, 100) = 95 ; low 95 high 100.
    peer = CompanyFinancials(ticker="P.NS", name="Peer", market_cap_cr=1000.0,
                             net_debt_cr=0.0, ebitda_cr=125.0, revenue_cr=500.0,
                             net_income_cr=50.0)
    tgt = CompanyFinancials(ticker="T.NS", name="Tgt", shares_out_cr=20.0,
                            ebitda_cr=250.0, revenue_cr=1000.0, net_income_cr=100.0,
                            net_debt_cr=100.0)
    r = compute_trading_comps(tgt, [peer, peer, peer])
    assert abs(r.median_ev_ebitda - 8.0) < 1e-9, r.median_ev_ebitda
    assert abs(r.implied_ps_ev_ebitda - 95.0) < 1e-9, r.implied_ps_ev_ebitda
    assert abs(r.implied_ps_pe - 100.0) < 1e-9, r.implied_ps_pe
    assert abs(r.value_per_share - 95.0) < 1e-9, r.value_per_share
    assert (r.per_share_low, r.per_share_high) == (95.0, 100.0), (r.per_share_low, r.per_share_high)
    print("trading_comps.py self-check OK:", r.narrative)
