"""Monte Carlo on Year 1-2 accretion: synergy, integration-cost and timing risk.

methodology:
    10,000 iterations, seeded rng (np.random.default_rng(42)) for exact
    reproducibility. The deal structure (S&U, PPA, share count) is fixed;
    only operating uncertainties are stochastic:
      - synergies: triangular(50%, 100%, 130%) x base run-rate
      - integration costs: lognormal with mean = base (sigma of log,
        default 0.25); zero base -> zero draws
      - synergy phase-in delay: discrete years {0: 70%, 1: 30%} — a delay
        of d shifts the phase-in schedule right by d years (year y uses
        phase_in[y-1-d], zero before the schedule starts)
    Each draw recomputes combined NI with the SAME formula as the
    deterministic engine (base NI is precomputed once from S&U + PPA), so a
    point-mass configuration reproduces the engine result exactly — that
    identity is asserted in tests. Outputs: P(Year-2 accretive), P5/P50/P95
    of Year-1 and Year-2 accretion %, and the raw sample arrays for
    histograms.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from data_layer import CompanyFinancials
from deal import DealTerms
from ppa import run_ppa
from sources_uses import build_sources_uses


@dataclass
class MCConfig:
    n_iterations: int = 10_000
    seed: int = 42
    synergy_triangular: tuple[float, float, float] = (0.5, 1.0, 1.3)  # x base: min/mode/max
    integration_log_sigma: float = 0.25
    delay_probs: dict[int, float] = field(default_factory=lambda: {0: 0.7, 1: 0.3})


@dataclass
class MCResult:
    y1_accretion: np.ndarray      # full samples, %
    y2_accretion: np.ndarray
    p_y2_accretive: float         # 0-1
    y1_p5: float
    y1_p50: float
    y1_p95: float
    y2_p5: float
    y2_p50: float
    y2_p95: float

    def memo_line(self) -> str:
        return (f"Probability of accretion by Year 2: {self.p_y2_accretive:.0%} "
                f"(P5: {self.y2_p5:+.1f}%, P95: {self.y2_p95:+.1f}%)")


def run_monte_carlo(
    acquirer: CompanyFinancials,
    target: CompanyFinancials,
    terms: DealTerms,
    open_offer_cost_cr: float = 0.0,
    open_offer_shares_frac: float = 0.0,
    config: MCConfig | None = None,
) -> MCResult:
    cfg = config or MCConfig()
    rng = np.random.default_rng(cfg.seed)
    n = cfg.n_iterations
    t = terms.tax_rate
    at = 1 - t

    # Fixed deal structure — identical to run_deal()
    su = build_sources_uses(acquirer, target, terms, open_offer_cost_cr)
    owned_frac = min(1.0, terms.stake_pct / 100 + open_offer_shares_frac)
    ppa = run_ppa(target, terms, su.equity_purchase_cr + su.open_offer_cost_cr,
                  owned_frac)
    base_ni = (acquirer.net_income_cr + owned_frac * target.net_income_cr
               - su.new_debt_cr * terms.debt_interest_rate * at
               - su.balance_sheet_cash_cr * terms.cash_yield_foregone * at
               - ppa.incremental_da_cr * at)
    pf_shares = acquirer.shares_out_cr + su.new_shares_cr
    eps0 = acquirer.net_income_cr / acquirer.shares_out_cr

    # Draws
    lo, mode, hi = cfg.synergy_triangular
    syn_mult = (rng.triangular(lo, mode, hi, n) if hi > lo
                else np.full(n, mode))
    synergies = terms.synergies_annual * syn_mult

    if terms.integration_costs > 0 and terms.include_integration_costs:
        sigma = cfg.integration_log_sigma
        mu = np.log(terms.integration_costs) - sigma**2 / 2  # E[X] = base
        integration = rng.lognormal(mu, sigma, n)
    else:
        integration = np.zeros(n)

    delays = rng.choice(list(cfg.delay_probs.keys()), size=n,
                        p=list(cfg.delay_probs.values()))

    def phase(year: int, d: np.ndarray) -> np.ndarray:
        idx = year - 1 - d
        table = np.array(terms.synergy_phase_in)
        return np.where(idx >= 0, table[np.clip(idx, 0, len(table) - 1)], 0.0)

    y1_ni = base_ni + synergies * phase(1, delays) * at - integration * at
    y2_ni = base_ni + synergies * phase(2, delays) * at
    y1_acc = (y1_ni / pf_shares / eps0 - 1) * 100
    y2_acc = (y2_ni / pf_shares / eps0 - 1) * 100

    p5_50_95 = lambda a: tuple(float(np.percentile(a, q)) for q in (5, 50, 95))
    y1_p5, y1_p50, y1_p95 = p5_50_95(y1_acc)
    y2_p5, y2_p50, y2_p95 = p5_50_95(y2_acc)

    return MCResult(
        y1_accretion=y1_acc, y2_accretion=y2_acc,
        p_y2_accretive=float((y2_acc > 0).mean()),
        y1_p5=y1_p5, y1_p50=y1_p50, y1_p95=y1_p95,
        y2_p5=y2_p5, y2_p50=y2_p50, y2_p95=y2_p95,
    )
