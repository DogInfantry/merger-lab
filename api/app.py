"""FastAPI backend for the premium web deal room (Option B).

methodology:
    A thin HTTP layer over the EXISTING engine — it calls the same
    build_deal_package + render_memo_html the Streamlit app and the sample
    generator use, so the interactive web app carries the full depth (RBI/SEBI
    stack, optimizer, Monte Carlo, DCF, trading comps, football field) with no
    parallel logic to drift.

    NO LLM / Anthropic / Claude calls anywhere in this path — the engine is
    pure Python (Non-negotiable #5). Public traffic never bills any API token.
    Only free data sources: yfinance (24h-cached) + the in-memory precedent seed.

    Deploys as its own HF Docker Space (see api/Dockerfile); the existing
    Streamlit Space is left untouched. CORS is open because every response is
    public, read-only, computed output — there is nothing to protect.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_layer import fetch_company            # noqa: E402
from deal import DealTerms                       # noqa: E402
from deal_package import build_deal_package      # noqa: E402
from memo_generator import render_memo_html      # noqa: E402
from precedent_db import get_connection, load_seed  # noqa: E402
from trading_comps import SECTOR_PEERS, fetch_sector_peers  # noqa: E402

app = FastAPI(title="Merger Lab API", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Precedent DB loaded once (read-only after seed — safe to share).
_CONN = get_connection(":memory:")
load_seed(_CONN)


class DealRequest(BaseModel):
    acquirer: str = Field(..., examples=["INFY.NS"])
    target: str = Field(..., examples=["PERSISTENT.NS"])
    codename: str = "Project X"
    sector: str | None = None                    # enables precedents + trading comps
    premium_pct: float = 18.0
    stake_pct: float = 100.0
    pct_cash: float = 50.0
    pct_debt: float = 60.0                        # % of cash needs from new bank debt
    debt_rate_pct: float = 8.5
    cash_yield_pct: float = 6.0
    synergies_cr: float = 400.0
    integration_cr: float = 200.0
    writeup_pct: float = 35.0
    acceptance_pct: float = 100.0
    wacc_pct: float = 12.0
    attested: bool = True


@app.get("/api/health")
def health():
    return {"status": "ok", "sectors": sorted(SECTOR_PEERS)}


@app.post("/api/deal")
def run_deal_endpoint(req: DealRequest):
    acq = fetch_company(req.acquirer)
    tgt = fetch_company(req.target)
    if not (acq.price and tgt.price and tgt.shares_out_cr):
        raise HTTPException(422, f"No usable market data for {req.acquirer} / {req.target}")

    sector = req.sector or None
    peers = fetch_sector_peers(sector, fetch_company,
                               exclude={req.acquirer, req.target}) if sector else None

    terms = DealTerms(
        offer_price=round(tgt.price * (1 + req.premium_pct / 100), 2),
        pct_cash=float(req.pct_cash), pct_stock=float(100 - req.pct_cash),
        pct_new_debt_of_cash_portion=float(req.pct_debt),
        debt_interest_rate=req.debt_rate_pct / 100,
        cash_yield_foregone=req.cash_yield_pct / 100,
        synergies_annual=req.synergies_cr, integration_costs=req.integration_cr,
        intangible_writeup_pct=req.writeup_pct / 100, tax_rate=0.2517,
        stake_pct=req.stake_pct,
    )
    pkg = build_deal_package(
        acq, tgt, terms, codename=req.codename,
        wacc=req.wacc_pct / 100, acceptance_assumption_pct=req.acceptance_pct,
        profitability_track_record=req.attested,
        precedent_conn=_CONN, sector=sector, peers=peers)

    return JSONResponse({
        "codename": pkg.codename,
        "acquirer": acq.name or req.acquirer,
        "target": tgt.name or req.target,
        "recommendation": pkg.recommendation,
        "rationale": pkg.recommendation_rationale,
        "year1_accretion_pct": round(pkg.ad.year1_accretion_pct, 2),
        "p_y2_accretive": round(pkg.mc.p_y2_accretive, 3),
        "rbi_pass": pkg.rbi.overall_pass,
        "dcf_per_share": round(pkg.dcf.value_per_share, 1) if pkg.dcf else None,
        "comps_per_share": (round(pkg.trading_comps.value_per_share, 1)
                            if pkg.trading_comps and pkg.trading_comps.value_per_share
                            else None),
        "offer_price": terms.offer_price,
        "memo_html": render_memo_html(pkg),
    })


if __name__ == "__main__":
    # Self-check: app wires and /health answers without any network or LLM call.
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    assert "IT Services" in r.json()["sectors"], r.json()
    print("api/app.py self-check OK:", r.json()["status"], "| sectors:", len(r.json()["sectors"]))
