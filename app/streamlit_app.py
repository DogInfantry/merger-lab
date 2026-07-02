"""MERGER LAB — Streamlit wrapper around the deal engine.

methodology:
    The dashboard is a WRAPPER: every number comes from build_deal_package()
    — the same frozen bundle that feeds the IC memo PDF and the Excel model,
    which remain the actual product (two big download buttons). Nothing is
    computed in this file beyond display formatting. Heavy work happens only
    after the sidebar form is submitted; company fetches are cached 1h.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import pandas as pd
import streamlit as st

from data_layer import fetch_company
from deal import DealTerms
from deal_package import build_deal_package
from excel_generator import generate_excel
from memo_generator import generate_memo, inr_cr
from precedent_db import SEED_CSV, get_connection, load_seed

st.set_page_config(page_title="MERGER LAB — India M&A Deal Room",
                   page_icon="🏛️", layout="wide")

GOLD, NAVY = "#C9A84C", "#070B14"
st.markdown(f"""<style>
  .badge {{ padding: 3px 12px; border-radius: 3px; font-weight: 700; font-size: 0.85rem; }}
  .pass {{ background: #123f28; color: #4ade80; }}
  .fail {{ background: #4a1512; color: #f87171; }}
  .rec  {{ border: 1.5px solid {GOLD}; padding: 18px 22px; margin: 8px 0 16px; }}
  .rec .v {{ color: {GOLD}; font-size: 1.6rem; font-weight: 800; }}
</style>""", unsafe_allow_html=True)

st.markdown(f"<h1 style='margin-bottom:0'>MERGER LAB</h1>"
            f"<p style='color:{GOLD};letter-spacing:2px;margin-top:0'>"
            f"INDIA M&A DEAL ROOM · RBI 2026 ACQUISITION-FINANCE FRAMEWORK</p>",
            unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner="Fetching company data…")
def _fetch(ticker: str):
    return fetch_company(ticker)


@st.cache_resource
def _precedents():
    conn = get_connection(":memory:")
    load_seed(conn, SEED_CSV)
    sectors = [r[0] for r in conn.execute(
        "SELECT DISTINCT sector FROM deals ORDER BY sector")]
    return conn, sectors


conn, sectors = _precedents()

# ---------------- sidebar: deal terms ----------------
with st.sidebar:
    st.header("Deal terms")
    with st.form("deal"):
        codename = st.text_input("Project codename", "Project Horizon")
        acq_ticker = st.text_input("Acquirer ticker (.NS/.BO)", "INFY.NS")
        tgt_ticker = st.text_input("Target ticker (.NS/.BO)", "PERSISTENT.NS")
        sector = st.selectbox("Sector (for precedent comps)", ["—"] + sectors)
        premium = st.slider("Offer premium %", -10.0, 60.0, 18.0, 0.5)
        stake = st.slider("Negotiated stake %", 26.0, 100.0, 100.0, 1.0)
        pct_cash = st.slider("% cash consideration", 0, 100, 50, 5)
        pct_debt = st.slider("% of cash needs from new bank debt", 0, 100, 60, 5)
        rate = st.slider("New debt interest rate % (MCLR + spread)", 6.0, 14.0, 8.5, 0.1)
        cash_yield = st.slider("Cash yield foregone %", 3.0, 9.0, 6.0, 0.1)
        synergies = st.number_input("Run-rate synergies (₹ Cr)", 0.0, 50_000.0, 400.0, 50.0)
        integration = st.number_input("Integration costs Y1 (₹ Cr)", 0.0, 20_000.0, 200.0, 50.0)
        writeup = st.slider("Intangible write-up % of excess", 0, 80, 35, 5)
        acceptance = st.radio("Open-offer acceptance assumption", [0.0, 50.0, 100.0],
                              index=2, horizontal=True)
        wacc = st.slider("WACC %", 8.0, 18.0, 12.0, 0.25)
        want_collar = st.checkbox("Price exchange-ratio collar (stock deals)", True)
        attested = st.checkbox("Acquirer has 3-yr profitability track record", True)
        run = st.form_submit_button("⚡ Run the deal", use_container_width=True)

if run:
    st.session_state["inputs"] = dict(
        codename=codename, acq=acq_ticker, tgt=tgt_ticker, sector=sector,
        premium=premium, stake=stake, pct_cash=pct_cash, pct_debt=pct_debt,
        rate=rate, cash_yield=cash_yield, synergies=synergies,
        integration=integration, writeup=writeup, acceptance=acceptance,
        wacc=wacc, want_collar=want_collar, attested=attested)

if "inputs" not in st.session_state:
    st.info("Set the deal terms in the sidebar and hit **Run the deal**. "
            "The IC memo PDF and linked Excel model — the actual product — "
            "download at the bottom.")
    st.stop()

I = st.session_state["inputs"]
acq, tgt = _fetch(I["acq"]), _fetch(I["tgt"])
if not (acq.price and tgt.price and tgt.shares_out_cr):
    st.error("Could not fetch usable market data for those tickers.")
    st.stop()

vol = None
if I["want_collar"] and I["pct_cash"] < 100:
    from collar import realized_vol_yf
    try:
        vol = realized_vol_yf(I["acq"])
    except Exception:
        st.warning("Realized vol unavailable — collar module skipped.")

terms = DealTerms(
    offer_price=round(tgt.price * (1 + I["premium"] / 100), 2),
    pct_cash=float(I["pct_cash"]), pct_stock=float(100 - I["pct_cash"]),
    pct_new_debt_of_cash_portion=float(I["pct_debt"]),
    debt_interest_rate=I["rate"] / 100, cash_yield_foregone=I["cash_yield"] / 100,
    synergies_annual=I["synergies"], integration_costs=I["integration"],
    intangible_writeup_pct=I["writeup"] / 100, tax_rate=0.2517,
    stake_pct=I["stake"],
)
with st.spinner("Running engine, optimizer, 10,000 Monte Carlo paths…"):
    pkg = build_deal_package(
        acq, tgt, terms, codename=I["codename"],
        wacc=I["wacc"] / 100, acceptance_assumption_pct=I["acceptance"],
        profitability_track_record=I["attested"], volatility=vol,
        precedent_conn=conn, sector=None if I["sector"] == "—" else I["sector"])

# ---------------- recommendation ----------------
st.markdown(
    f"<div class='rec'><span class='v'>{pkg.recommendation}</span><br>"
    f"{pkg.recommendation_rationale}</div>", unsafe_allow_html=True)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Year-1 EPS impact", f"{pkg.ad.year1_accretion_pct:+.2f}%")
k2.metric("P(accretive by Y2)", f"{pkg.mc.p_y2_accretive:.0%}")
k3.metric("Net value created", inr_cr(pkg.value_bridge.net_value_created_cr))
k4.metric("Total uses", inr_cr(pkg.su.total_uses_cr))

# ---------------- RBI panel ----------------
st.subheader("RBI acquisition-finance compliance")
cols = st.columns(len(pkg.rbi.checks))
for col, c in zip(cols, pkg.rbi.checks):
    cls = "pass" if c.status == "PASS" else "fail"
    col.markdown(f"<span class='badge {cls}'>{c.status}</span><br>"
                 f"<small>{c.name}</small><br><b>{c.value}</b>",
                 unsafe_allow_html=True)
st.caption(pkg.optimizer.narrative)

# ---------------- results ----------------
left, right = st.columns(2)
with left:
    st.subheader("Accretion / dilution")
    st.dataframe(pd.DataFrame([{
        "Year": y.year, "Combined NI (₹ Cr)": round(y.combined_ni_cr, 0),
        "PF EPS (₹)": round(y.pf_eps, 2),
        "Accretion %": round(y.accretion_pct, 2)} for y in pkg.ad.years]),
        hide_index=True, use_container_width=True)
    st.caption(f"Break-even synergies: {inr_cr(pkg.ad.breakeven_synergies_cr)} · "
               f"{pkg.ad.heuristic_note}")
    st.subheader("Contribution vs ownership")
    st.dataframe(pkg.contribution, hide_index=True, use_container_width=True)
    if pkg.contribution_flag:
        st.warning(pkg.contribution_flag)
with right:
    st.subheader("Monte Carlo — Year-2 accretion")
    counts, edges = np.histogram(pkg.mc.y2_accretion, bins=40)
    st.bar_chart(pd.DataFrame(
        {"count": counts},
        index=np.round((edges[:-1] + edges[1:]) / 2, 2)), color=GOLD)
    st.caption(pkg.mc.memo_line())
    if pkg.collar:
        st.subheader("Collar payoff (per target share)")
        st.line_chart(pkg.collar.payoff.set_index("acquirer_price"),
                      color=[GOLD, "#5a6170"])

st.subheader("Sensitivity — Year-1 accretion %")
_heat = lambda v: (f"background-color: rgba(192,57,43,{min(1, abs(v) / 8) * .5 + .06:.2f})"
                   if v < 0 else
                   f"background-color: rgba(39,124,74,{min(1, v / 8) * .5 + .06:.2f})")
t1, t2 = st.tabs(["Premium × synergies", "% cash × premium"])
t1.dataframe(pkg.grid_premium_synergies.style.map(_heat).format("{:+.2f}"),
             use_container_width=True)
t2.dataframe(pkg.grid_cash_premium.style.map(_heat).format("{:+.2f}"),
             use_container_width=True)

if pkg.value_bridge.mechanical_accretion_warning:
    st.error("⚠ Accretive but value-destructive — accretion is P/E arbitrage, "
             "not economics.")

# ---------------- THE PRODUCT: downloads ----------------
st.divider()
st.subheader("Deliverables")
d1, d2 = st.columns(2)
with tempfile.TemporaryDirectory() as td:
    memo_path = generate_memo(pkg, Path(td) / "memo.pdf")
    xlsx_path = generate_excel(pkg, Path(td) / "model.xlsx")
    slug = I["codename"].replace(" ", "_")
    d1.download_button("📄 Download IC Memo (PDF)", memo_path.read_bytes(),
                       file_name=f"{slug}_IC_Memo{memo_path.suffix}",
                       use_container_width=True, type="primary")
    d2.download_button("📊 Download Excel Model", xlsx_path.read_bytes(),
                       file_name=f"{slug}_Model.xlsx",
                       use_container_width=True, type="primary")

st.caption("MERGER LAB · illustrative analysis on public data · not investment "
           "advice · RBI/SEBI parameters to be verified against master directions")
