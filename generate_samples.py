"""Generate the pre-run sample case studies (memo PDF + Excel per deal).

methodology:
    Three ILLUSTRATIVE large-cap demo deals — real listed companies, live
    yfinance market data, but hypothetical transactions with assumption sets
    invented for demonstration (synergies ~2.5-3% of target revenue,
    premiums near sector precedent medians). Every output is labeled
    ILLUSTRATIVE. Also refreshes site/assets/ so the Vercel landing page
    always embeds the latest hero memo, and captures a PNG preview of the
    memo for the README via headless Edge/Chrome.

Run: python generate_samples.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from collar import realized_vol_yf
from data_layer import fetch_company
from deal import DealTerms
from deal_package import build_deal_package
from excel_generator import generate_excel
from memo_generator import _chromium_path, generate_memo, render_memo_html
from precedent_db import get_connection, load_seed
from trading_comps import fetch_sector_peers

DEALS = [
    dict(
        codename="Project Horizon", sector="IT Services",
        acquirer="INFY.NS", target="PERSISTENT.NS",
        premium=0.18, stake=100.0, pct_cash=40.0, pct_debt=50.0,
        rationale=[
            "Adds a high-growth digital-engineering franchise to a scaled services platform",
            "Client roster complementarity: BFSI depth meets ISV/hi-tech engineering",
            "Illustrative synergies at ~2.5% of target revenue (cross-sell + pyramid costs)",
        ],
        risks=["Attrition of key engineering talent post-close",
               "Revenue dis-synergies from client overlap audits",
               "Stock consideration exposes target holders to acquirer multiple compression"],
    ),
    dict(
        codename="Project Bastion", sector="Cement",
        acquirer="ULTRACEMCO.NS", target="JKCEMENT.NS",
        premium=0.15, stake=64.0, pct_cash=100.0, pct_debt=65.0,
        rationale=[
            "Consolidates grey-cement capacity in North India amid the post-RBI-2026 M&A wave",
            "Promoter block purchase (64%) with mandatory 26% open offer — full SAST mechanics on display",
            "Illustrative synergies from freight/clinker network optimization",
        ],
        risks=["CCI review of regional market-share concentration",
               "MPS breach at high open-offer acceptance forces sell-down or delisting attempt",
               "Cement cycle timing risk on acquired capacity"],
    ),
    dict(
        codename="Project Meridian", sector="Metals & Mining",
        acquirer="HINDALCO.NS", target="NATIONALUM.NS",
        premium=0.12, stake=51.0, pct_cash=100.0, pct_debt=60.0,
        rationale=[
            "Integrates low-cost bauxite/alumina capacity upstream of acquirer's smelting network",
            "Illustrative PSU-divestment structure: 51% block + mandatory 26% open offer",
            "Low-multiple target — earnings yield comfortably above after-tax debt cost under RBI 2026 financing",
        ],
        risks=["Aluminium price cycle turns before synergy phase-in completes",
               "PSU workforce integration and government-approval timeline",
               "MPS sell-down obligation at high open-offer acceptance"],
    ),
]


def main() -> None:
    conn = get_connection(":memory:")
    load_seed(conn)
    hero_assets: dict[str, Path] = {}

    for cfg in DEALS:
        print(f"\n=== {cfg['codename']}: {cfg['acquirer']} -> {cfg['target']} ===")
        acq = fetch_company(cfg["acquirer"])
        tgt = fetch_company(cfg["target"])
        assert acq.price and tgt.price and tgt.shares_out_cr, \
            f"market data unavailable for {cfg['codename']}"

        synergies = round((tgt.revenue_cr or 0) * 0.027, -1) or 100.0
        terms = DealTerms(
            offer_price=round(tgt.price * (1 + cfg["premium"]), 2),
            pct_cash=cfg["pct_cash"], pct_stock=100 - cfg["pct_cash"],
            pct_new_debt_of_cash_portion=cfg["pct_debt"],
            debt_interest_rate=0.085,      # illustrative MCLR + spread; RBI DBIE
            cash_yield_foregone=0.06,
            synergies_annual=synergies,
            integration_costs=round(synergies * 0.5, -1),
            intangible_writeup_pct=0.35, intangible_life_years=8,
            tax_rate=0.2517, stake_pct=cfg["stake"],
        )
        vol = None
        if terms.pct_stock > 0:
            try:
                vol = realized_vol_yf(cfg["acquirer"])
            except Exception as e:
                print(f"  vol unavailable ({e}); collar skipped")

        peers = fetch_sector_peers(
            cfg["sector"], fetch_company,
            exclude={cfg["acquirer"], cfg["target"]})

        pkg = build_deal_package(
            acq, tgt, terms, codename=cfg["codename"],
            strategic_rationale=cfg["rationale"], key_risks=cfg["risks"],
            volatility=vol, precedent_conn=conn, sector=cfg["sector"],
            peers=peers)

        slug = cfg["codename"].lower().replace(" ", "_")
        out_dir = ROOT / "samples" / slug
        memo = generate_memo(pkg, out_dir / f"{slug}_ic_memo.pdf")
        xlsx = generate_excel(pkg, out_dir / f"{slug}_model.xlsx")
        # Web-native premium memo for the Vercel deal room (real HTML, not a PDF embed)
        web_dir = ROOT / "site" / "deals"
        web_dir.mkdir(parents=True, exist_ok=True)
        (web_dir / f"{slug}.html").write_text(render_memo_html(pkg), encoding="utf-8")
        print(f"  {pkg.recommendation} | Y1 {pkg.ad.year1_accretion_pct:+.2f}% | "
              f"P(Y2) {pkg.mc.p_y2_accretive:.0%} | memo {memo.name} "
              f"({memo.stat().st_size // 1024} KB) | model {xlsx.name}")
        hero_assets[slug] = memo

        if cfg["codename"] == "Project Horizon":   # hero deal for site + README
            site_assets = ROOT / "site" / "assets"
            site_assets.mkdir(parents=True, exist_ok=True)
            shutil.copy2(memo, site_assets / memo.name)
            shutil.copy2(xlsx, site_assets / xlsx.name)
            _screenshot_memo(pkg, ROOT / "docs" / "memo_preview.png")

    # remaining sample downloads for the landing page cards
    site_assets = ROOT / "site" / "assets"
    for slug in ("project_bastion", "project_meridian"):
        d = ROOT / "samples" / slug
        for f in d.glob("*"):
            shutil.copy2(f, site_assets / f.name)
    print("\nsamples + site assets ready")


def _screenshot_memo(pkg, png_path: Path) -> None:
    """README hero image: headless-Chromium screenshot of the memo cover."""
    browser = _chromium_path()
    if not browser:
        print("  no chromium found; README screenshot skipped")
        return
    png_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "memo.html"
        src.write_text(render_memo_html(pkg), encoding="utf-8")
        subprocess.run(
            [browser, "--headless", "--disable-gpu",
             "--window-size=1080,1420", "--hide-scrollbars",
             f"--screenshot={png_path}", src.as_uri()],
            check=True, capture_output=True, timeout=120)
    print(f"  README preview -> {png_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
