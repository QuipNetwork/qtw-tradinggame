"""Static configuration constants.

Single source of truth for all magic numbers — bankroll, slider ranges,
estimation windows, QUBO hyperparameters, solver deadlines.
"""

from __future__ import annotations

import os

# -----------------------------------------------------------------------------
# Bankroll and basket
# -----------------------------------------------------------------------------

BANKROLL_USD: float = 10_000.0
# Smallest basket the strategy meaningfully optimizes over; the kiosk's Select
# button should mirror this gate.
MIN_BASKET_SIZE: int = 3

# -----------------------------------------------------------------------------
# Estimation windows (hours)
# -----------------------------------------------------------------------------

# Risk lookback T feeding Σ — fixed, not user-facing. 30 days of hourly bars;
# can extend up to 2160h (90d, the assets-api retention cap).
SIGMA_WINDOW_HOURS: int = 720
# Return lookback τ feeding μ — fixed, not user-facing. 7 days of hourly bars.
MU_WINDOW_HOURS: int = 168

# -----------------------------------------------------------------------------
# Estimation from ragged real data (μ, Σ)
# -----------------------------------------------------------------------------

# We never fabricate returns: closed-hour and not-yet-listed gaps are missing,
# not zero, and a stock's overnight jump is excluded (no consecutive-hour pair
# spans it). So assets carry unequal observation counts — crypto ~720/30d,
# stocks ~140, a freshly-listed name far fewer — and Σ is built from pairwise
# overlaps, which can be ragged or indefinite. These knobs keep μ/Σ robust;
# none are user-facing.

# Minimum real returns for a trusted mean/variance. Below it, μ falls back to 0
# (hold for diversification, don't chase a mean from a handful of points) and
# the variance to its class-median floor (so a thin asset can't read as calm).
MIN_RETURN_OBS: int = 24
# Minimum overlapping returns for a covariance cell; below it cov(i,j) = 0
# (treat the pair as uncorrelated rather than trust a few-sample estimate).
MIN_COV_PAIRS: int = 20
# Shrinkage toward the diagonal, Σ ← (1−δ)Σ + δ·diag(Σ): damps noisy off-diagonal
# correlations. A stability step, NOT a PSD guarantee (see COV_EIG_FLOOR_REL).
COV_SHRINKAGE: float = 0.2
# Implied-correlation cap: few-sample overlaps can imply |corr| > 1 against the
# full-window variances; clip covariances so |corr| ≤ this before shrinkage.
COV_MAX_ABS_CORR: float = 0.99
# PSD repair after shrinkage: floor eigenvalues at this fraction of the mean
# variance so the matrix the solvers see is always positive semidefinite.
COV_EIG_FLOOR_REL: float = 1e-4
# Last-resort hourly variance when a whole class has too little data to floor
# against (degenerate baskets only).
COV_DEFAULT_VAR: float = 1e-4

# -----------------------------------------------------------------------------
# Slider → param ranges (single source of truth, used by slider_map)
# -----------------------------------------------------------------------------

GAMMA_RANGE: tuple[float, float] = (0.5, 20.0)  # log-scaled

# Per-asset cap is RELATIVE to the basket (mirrors mvp/src/utils/strategy.ts::
# maxPositionCapPct): slider sweeps from equal weight (1/n — maximally
# diversified) up to W_MAX_CEILING in a single asset. A 1-asset basket is
# always 100%.
W_MAX_CEILING: float = 0.5

# Participation floor, not user-facing: w_min = MIN_POSITION_FRACTION/n, so
# every basket asset the player picked shows up in the portfolio. n·w_min ≤ 1
# always holds since MIN_POSITION_FRACTION ≤ 1.
MIN_POSITION_FRACTION: float = 0.25

# Rebalance-frequency slider tiers → scheduled re-optimization cadence (hours).
# Hourly is the hard cap: quantum jobs cost real money (mirrors strategy.ts).
REBALANCE_TIERS_HOURS: tuple[int, ...] = (24, 8, 4, 2, 1)

# -----------------------------------------------------------------------------
# QUBO encoding hyperparameters
# -----------------------------------------------------------------------------

# Bits per asset across [w_min, w_max]. Large baskets drop to 2 bits: feasibility
# on Advantage_system4 is governed by variable count, not bit depth, so halving
# the variables is what claws back feasible reads. Hardware sweep (2026-06-19,
# ~3.4s QPU): 18 assets b=3 (54 vars) → 17/500 feasible vs b=2 (36 vars) → 67/500
# — b=3 is dominated, so skip straight from b=4 to b=2. Fewer bits = coarser grid
# (4 levels; simplex normalization absorbs it). Baskets >~20 assets stay QPU-
# infeasible regardless (28 assets b=2 = 56 vars → ~0/500) and lean on SA/Gurobi.
BIT_PRECISION: int = 4
BIT_PRECISION_LARGE: int = 2
QUBO_PREFERRED_MAX_VARS: int = 60  # use BIT_PRECISION while n·b stays within this
# Penalty:objective PEAK-COEFFICIENT ratio: max|A_budget| = mult × max|A_obj|
# (encoder normalizes λ_sum by u_max², so this ratio is invariant to basket size,
# bit depth, and w_max). Under the old un-normalized λ_sum = mult × max|A_obj|,
# the *effective* ratio was mult·u_max² and swung from ~0.15 (low w_max) to ~39
# (w_max=0.5) for a 25-asset basket — the low end is where Σw drifted. 12.0 sits
# in the empirically-working band (~10–40, mid max-position slider), high enough
# to hold the budget across all configs, low enough to keep the objective above
# QPU coupler precision. NOTE: re-verify on hardware (`qtw verify-dwave`) and
# re-tune within ~10–40 if large-basket feasibility regresses.
PENALTY_MULT_BUDGET: float = 12.0

# A QUBO solver's weights live on a discrete grid (and the QPU adds analog
# noise), so Σw=1 is only approximate. Decoded sums within this tolerance of 1
# are normalized onto the simplex before the feasibility gate; the box check
# stays as the backstop (a >10% rescale pushes weights past w_min/w_max + ε,
# so genuinely bad reads still fail).
QUBO_NORMALIZE_TOL: float = 0.10

# -----------------------------------------------------------------------------
# Feasibility tolerances (V0 quality bar)
# -----------------------------------------------------------------------------

EPS_BUDGET: float = 1e-3  # |Σwᵢ − 1| < EPS_BUDGET
EPS_BOX: float = 1e-3  # wᵢ ≤ w_max + EPS_BOX

# -----------------------------------------------------------------------------
# Race field
# -----------------------------------------------------------------------------

# Gurobi races locally during development but is NOT deployed to production
# (licensing) — there it remains the offline oracle only, and the live race is
# SA (CPU) vs D-Wave (QPU). GUROBI_IN_RACE=0 to preview the production field.
GUROBI_IN_RACE: bool = os.environ.get("GUROBI_IN_RACE", "1").lower() not in ("0", "false")

# -----------------------------------------------------------------------------
# D-Wave (joins the race only when DWAVE_API_TOKEN is set)
# -----------------------------------------------------------------------------

# All knobs are env-overridable for tuning sweeps, e.g.
#   DWAVE_CHAIN_STRENGTH_PREFACTOR=4 qtw verify-dwave
DWAVE_NUM_READS: int = int(os.environ.get("DWAVE_NUM_READS", 500))  # fallback / verify-dwave
DWAVE_ANNEAL_TIME_US: int = int(os.environ.get("DWAVE_ANNEAL_TIME_US", 100))

# num_reads scaled to QUBO size (logical vars = n_assets × bits). Small problems
# are feasibility-rich, so fewer reads suffice and the lower QPU access time
# (D-Wave's reported race time) helps it WIN; large problems are feasibility-poor,
# so more reads raise the odds of catching a rare feasible sample (it won't win on
# speed at that size regardless). Tiers: (max_vars_inclusive, num_reads), first
# match wins. ~feasibility from the 2026-06-19 sweep: ≤30v rich, 31-48v moderate,
# >48v poor. Reads ≈ 16ms + n×0.29ms QPU, so 150/350/600 ≈ 60/120/190 ms.
DWAVE_READS_BY_VARS: tuple[tuple[int, int], ...] = ((30, 150), (48, 350), (90, 600))
# Chain strength = uniform torque compensation × this prefactor. Raise if
# verify-dwave reports chain breaks above ~5% (long chains need stronger bonds).
# ×3 from hardware sweeps: ×2 leaves ~17% chain breaks at 75+ vars; ×3 gives
# 0.4% there with margin to spare at small baskets.
DWAVE_CHAIN_STRENGTH_PREFACTOR: float = float(os.environ.get("DWAVE_CHAIN_STRENGTH_PREFACTOR", 3.0))

# Per-agent QPU admission budget. This limits optimization attempts that would
# include D-Wave in the race; CPU-only runs are unaffected.
QPU_BUDGET_MAX_ATTEMPTS: int = int(os.environ.get("QPU_BUDGET_MAX_ATTEMPTS", 3))
QPU_BUDGET_WINDOW_S: int = int(os.environ.get("QPU_BUDGET_WINDOW_S", 600))

# -----------------------------------------------------------------------------
# Solver deadlines (seconds)
# -----------------------------------------------------------------------------

SOLVER_DEADLINE_S: float = 2.0  # per-solver wall-clock budget
RACE_OVERALL_DEADLINE_S: float = 3.0  # outer cap on the parallel race

# -----------------------------------------------------------------------------
# MTM tick cadence (seconds)
# -----------------------------------------------------------------------------

MTM_TICK_S: float = 3.0
REBALANCE_CHECK_TICK_S: float = 15.0
REBALANCE_RETRY_BACKOFF_S: float = 60.0
VALUATION_SNAPSHOT_INTERVAL_S: float = float(os.environ.get("VALUATION_SNAPSHOT_INTERVAL_S", 60.0))

# -----------------------------------------------------------------------------
# Persistence
# -----------------------------------------------------------------------------

# Unset -> in-memory stores (tests/offline/local default). Set -> SQL-backed
# stores, typically Supabase Postgres in production.
DATABASE_URL: str | None = os.environ.get("DATABASE_URL")
# Marks rows created by local/dev/booth runs so a single Supabase project can be
# cleaned up safely after local testing.
APP_ENV: str = os.environ.get("APP_ENV", "local")

# -----------------------------------------------------------------------------
# Market data source
# -----------------------------------------------------------------------------

# "assets-api" → the assets-api price-indexing service (REST, SQLite-backed);
# "synthetic" → deterministic stand-in (no network — tests and offline demos).
MARKET_DATA_SOURCE: str = os.environ.get("MARKET_DATA_SOURCE", "assets-api")
# Live deployment (28-asset registry). Override with a local Docker address
# (http://127.0.0.1:8080) for offline work, or MARKET_DATA_SOURCE=synthetic.
ASSETS_API_BASE_URL: str = os.environ.get(
    "ASSETS_API_BASE_URL", "https://asset-tracker.quip.network"
)
ASSETS_API_TIMEOUT_S: float = 10.0
ASSETS_API_RETRIES: int = int(os.environ.get("ASSETS_API_RETRIES", 2))
ASSETS_API_RETRY_BACKOFF_S: float = float(os.environ.get("ASSETS_API_RETRY_BACKOFF_S", 0.25))
SYNTHETIC_SEED: int = 20260625  # booth day — deterministic synthetic history

# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------

# Origins allowed by CORS. The deployed MVP plus local dev.
CORS_ORIGINS: tuple[str, ...] = (
    "https://qtw-tradinggame.netlify.app",
    "https://qtw.quip.network",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
QR_BASE_URL: str = os.environ.get("QR_BASE_URL", "https://qtw.quip.network")
MTM_ERROR_LOG_INTERVAL_S: float = float(os.environ.get("MTM_ERROR_LOG_INTERVAL_S", 30.0))
