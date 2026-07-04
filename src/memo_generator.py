"""IC memo generator: Jinja2 HTML -> PDF (WeasyPrint, else headless Edge/Chrome).

methodology:
    The memo is rendered from templates/ic_memo.html with every number taken
    from a frozen DealPackage — no arithmetic happens in the template. Charts
    (MC histogram, collar payoff) are generated as inline SVG in Python, so
    there is no matplotlib dependency and the PDF is fully vector. Sensitivity
    grids are heat-styled HTML tables (red = dilutive, green = accretive,
    intensity scaled to the grid's max absolute value).
    PDF engines, in order: WeasyPrint if importable (Linux/Mac); otherwise
    headless Microsoft Edge/Chrome --print-to-pdf (Windows default); else the
    rendered HTML is kept and a warning logged. Page numbers render under
    WeasyPrint (@page margin boxes); Chromium prints the fixed footer band on
    every page but omits page numbers — documented limitation.
    Indian formatting: ₹ with Indian digit grouping (last 3, then pairs),
    e.g. ₹6,28,000 Cr.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader

from deal_package import DealPackage

log = logging.getLogger("merger_lab.memo")
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


# --- formatting filters -------------------------------------------------------

def indian_group(n: float) -> str:
    """1234567 -> '12,34,567' (Indian digit grouping)."""
    s = f"{int(round(abs(n))):d}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + s


def _missing(x: float | None) -> bool:
    """True for None or float NaN (pandas to_dict yields NaN for blank cells)."""
    return x is None or (isinstance(x, float) and x != x)


def inr_cr(x: float | None, decimals: int = 0) -> str:
    """INR crore with Indian digit grouping; decimals only for small values."""
    if _missing(x):
        return "n/a"
    if decimals and abs(x) < 100_000:
        return f"₹{x:,.{decimals}f} Cr"
    return f"₹{indian_group(x)} Cr"


def pct(x: float | None, decimals: int = 1) -> str:
    return "n/a" if _missing(x) else f"{x:+.{decimals}f}%"


def num(x: float | None, decimals: int = 2) -> str:
    return "n/a" if _missing(x) else f"{x:,.{decimals}f}"


# --- SVG charts ---------------------------------------------------------------

def svg_histogram(samples: np.ndarray, title: str, width=640, height=230) -> str:
    counts, edges = np.histogram(samples, bins=32)
    pad_l, pad_b, pad_t = 10, 34, 26
    plot_w, plot_h = width - 2 * pad_l, height - pad_b - pad_t
    max_c = counts.max() or 1
    bw = plot_w / len(counts)
    lo, hi = edges[0], edges[-1]

    def x_of(v):  # data -> px
        return pad_l + (v - lo) / (hi - lo) * plot_w

    bars = "".join(
        f'<rect x="{pad_l + i * bw:.1f}" y="{pad_t + plot_h * (1 - c / max_c):.1f}" '
        f'width="{bw - 1:.1f}" height="{plot_h * c / max_c:.1f}" fill="#070B14" opacity="0.85"/>'
        for i, c in enumerate(counts))
    p50 = float(np.percentile(samples, 50))
    zero = (f'<line x1="{x_of(0):.1f}" y1="{pad_t}" x2="{x_of(0):.1f}" '
            f'y2="{pad_t + plot_h}" stroke="#999" stroke-dasharray="4,3"/>'
            if lo < 0 < hi else "")
    return f"""<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img">
<text x="{pad_l}" y="16" font-size="12" fill="#070B14" font-weight="bold">{title}</text>
{bars}{zero}
<line x1="{x_of(p50):.1f}" y1="{pad_t}" x2="{x_of(p50):.1f}" y2="{pad_t + plot_h}" stroke="#C9A84C" stroke-width="2"/>
<text x="{x_of(p50) + 4:.1f}" y="{pad_t + 12}" font-size="10" fill="#C9A84C">P50 {p50:+.1f}%</text>
<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" y2="{pad_t + plot_h}" stroke="#070B14"/>
<text x="{pad_l}" y="{height - 8}" font-size="10" fill="#444">{lo:+.1f}%</text>
<text x="{width - pad_l}" y="{height - 8}" font-size="10" fill="#444" text-anchor="end">{hi:+.1f}%</text>
</svg>"""


def svg_payoff(payoff: pd.DataFrame, floor: float, cap: float,
               width=640, height=240) -> str:
    x, y_fix, y_col = (payoff["acquirer_price"].to_numpy(),
                       payoff["fixed_ratio_value"].to_numpy(),
                       payoff["collared_value"].to_numpy())
    pad, pad_t = 44, 22
    pw, ph = width - 2 * pad, height - pad - pad_t
    ylo, yhi = min(y_fix.min(), y_col.min()) * 0.95, max(y_fix.max(), y_col.max()) * 1.05

    def X(v): return pad + (v - x[0]) / (x[-1] - x[0]) * pw
    def Y(v): return pad_t + (1 - (v - ylo) / (yhi - ylo)) * ph

    line = lambda ys: " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(x, ys))
    vline = lambda v, lbl: (
        f'<line x1="{X(v):.1f}" y1="{pad_t}" x2="{X(v):.1f}" y2="{pad_t + ph}" '
        f'stroke="#C9A84C" stroke-dasharray="5,4"/>'
        f'<text x="{X(v) + 3:.1f}" y="{pad_t + 12}" font-size="10" fill="#C9A84C">{lbl}</text>')
    return f"""<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img">
<text x="{pad}" y="14" font-size="12" fill="#070B14" font-weight="bold">Value per target share at close (₹)</text>
<polyline points="{line(y_fix)}" fill="none" stroke="#9aa2ad" stroke-width="1.5" stroke-dasharray="6,4"/>
<polyline points="{line(y_col)}" fill="none" stroke="#070B14" stroke-width="2.5"/>
{vline(floor, f"floor ₹{floor:,.0f}")}{vline(cap, f"cap ₹{cap:,.0f}")}
<line x1="{pad}" y1="{pad_t + ph}" x2="{pad + pw}" y2="{pad_t + ph}" stroke="#070B14"/>
<text x="{pad}" y="{height - 6}" font-size="10" fill="#444">₹{x[0]:,.0f}</text>
<text x="{pad + pw}" y="{height - 6}" font-size="10" fill="#444" text-anchor="end">₹{x[-1]:,.0f}</text>
<text x="{pad + pw}" y="{Y(y_fix[-1]) - 6:.1f}" font-size="10" fill="#9aa2ad" text-anchor="end">fixed ratio</text>
<text x="{pad + pw}" y="{Y(y_col[-1]) + 14:.1f}" font-size="10" fill="#070B14" text-anchor="end">collared</text>
</svg>"""


def heat_table(df: pd.DataFrame) -> str:
    """DataFrame -> HTML table, red (dilutive) to green (accretive) heat cells."""
    m = max(abs(float(df.values.min())), abs(float(df.values.max()))) or 1.0
    head = "<tr><th>" + (df.index.name or "") + "</th>" + \
        "".join(f"<th>{c}</th>" for c in df.columns) + "</tr>"
    rows = []
    for idx, row in df.iterrows():
        cells = []
        for v in row:
            alpha = 0.08 + 0.42 * min(1.0, abs(v) / m)
            rgb = "192,57,43" if v < 0 else "39,124,74"
            cells.append(f'<td style="background:rgba({rgb},{alpha:.2f})">{v:+.2f}</td>')
        rows.append(f"<tr><th>{idx}</th>{''.join(cells)}</tr>")
    return f'<table class="grid heat">{head}{"".join(rows)}</table>'


def svg_football_field(rows: list[dict], current: float | None,
                       offer: float | None, width=640, row_h=34) -> str:
    """Valuation ranges as horizontal bars + current/offer markers (₹/share)."""
    vals = [v for r in rows for v in (r["low"], r["high"])]
    vals += [x for x in (current, offer) if x]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    lo, hi = lo - span * 0.08, hi + span * 0.08
    pad_l, pad_r, pad_t = 150, 24, 26
    pw = width - pad_l - pad_r
    height = pad_t + len(rows) * row_h + 34

    def X(v):
        return pad_l + (v - lo) / (hi - lo) * pw

    bars = []
    for i, r in enumerate(rows):
        y = pad_t + i * row_h + 6
        x0, x1, xm = X(r["low"]), X(r["high"]), X(r["mid"])
        bars.append(
            f'<text x="{pad_l - 8}" y="{y + 14:.0f}" font-size="10.5" fill="#070B14" '
            f'text-anchor="end">{r["method"]}</text>'
            f'<rect x="{x0:.1f}" y="{y:.0f}" width="{max(x1 - x0, 1):.1f}" height="18" '
            f'rx="2" fill="#070B14" opacity="0.82"/>'
            f'<line x1="{xm:.1f}" y1="{y - 2:.0f}" x2="{xm:.1f}" y2="{y + 20:.0f}" '
            f'stroke="#C9A84C" stroke-width="2"/>'
            f'<text x="{x0 - 3:.1f}" y="{y + 13:.0f}" font-size="8.5" fill="#5a6170" '
            f'text-anchor="end">₹{r["low"]:,.0f}</text>'
            f'<text x="{x1 + 3:.1f}" y="{y + 13:.0f}" font-size="8.5" fill="#5a6170">'
            f'₹{r["high"]:,.0f}</text>')

    def marker(v, lbl, colour):
        if not v:
            return ""
        return (f'<line x1="{X(v):.1f}" y1="{pad_t - 6}" x2="{X(v):.1f}" '
                f'y2="{pad_t + len(rows) * row_h:.0f}" stroke="{colour}" '
                f'stroke-width="1.5" stroke-dasharray="5,3"/>'
                f'<text x="{X(v):.1f}" y="{pad_t + len(rows) * row_h + 14:.0f}" '
                f'font-size="9" fill="{colour}" text-anchor="middle">{lbl} ₹{v:,.0f}</text>')

    return f"""<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img">
<text x="{pad_l - 8}" y="14" font-size="11.5" fill="#070B14" font-weight="bold" text-anchor="end">Valuation range (₹/share)</text>
{''.join(bars)}
{marker(current, 'mkt', '#5a6170')}{marker(offer, 'offer', '#b02a1e')}
</svg>"""


# --- rendering ----------------------------------------------------------------

def render_memo_html(pkg: DealPackage) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    env.filters.update(inr=inr_cr, pct=pct, num=num)
    ctx = dict(
        pkg=pkg,
        mc_hist_svg=svg_histogram(pkg.mc.y2_accretion,
                                  "Year-2 accretion distribution (10,000 iterations)"),
        collar_svg=(svg_payoff(pkg.collar.payoff, pkg.collar.floor_price,
                               pkg.collar.cap_price) if pkg.collar else None),
        heat_prem_syn=heat_table(pkg.grid_premium_synergies),
        heat_cash_prem=heat_table(pkg.grid_cash_premium),
        comps_rows=(pkg.sector_comps.head(10).to_dict("records")
                    if pkg.sector_comps is not None else []),
        football_svg=(svg_football_field(pkg.valuation_ranges, pkg.target.price,
                                         pkg.terms.offer_price)
                      if pkg.valuation_ranges else None),
        tc_peer_rows=(pkg.trading_comps.peer_table.to_dict("records")
                      if pkg.trading_comps is not None else []),
    )
    return env.get_template("ic_memo.html").render(**ctx)


def _chromium_path() -> str | None:
    for name in ("msedge", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(p).exists():
            return p
    return None


def html_to_pdf(html: str, pdf_path: str | Path) -> Path:
    """WeasyPrint if available, else headless Edge/Chrome, else keep HTML."""
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from weasyprint import HTML  # type: ignore
        HTML(string=html).write_pdf(str(pdf_path))
        return pdf_path
    except ImportError:
        pass

    browser = _chromium_path()
    if browser:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "memo.html"
            src.write_text(html, encoding="utf-8")
            subprocess.run(
                [browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                 f"--print-to-pdf={pdf_path}", src.as_uri()],
                check=True, capture_output=True, timeout=120)
        return pdf_path

    fallback = pdf_path.with_suffix(".html")
    fallback.write_text(html, encoding="utf-8")
    log.warning("No PDF engine found; wrote HTML to %s", fallback)
    return fallback


def generate_memo(pkg: DealPackage, pdf_path: str | Path) -> Path:
    """Render the IC memo for a deal package and write the PDF."""
    return html_to_pdf(render_memo_html(pkg), pdf_path)
