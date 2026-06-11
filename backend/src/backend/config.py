"""Static configuration constants.

Single source of truth for all magic numbers — bankroll, slider ranges,
estimation windows, QUBO hyperparameters, solver deadlines.
"""

from __future__ import annotations

# -----------------------------------------------------------------------------
# Bankroll and basket
# -----------------------------------------------------------------------------

BANKROLL_USD: float = 10_000.0
N_ASSETS: int = 25  # full universe (14 crypto + 11 stocks); players pick a subset
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

# Turnover penalty λ_t‖w − w_prev‖², applied on retunes only (first solve has
# no holdings to anchor to, so λ_t = 0 and w_ref is irrelevant). Scaled to the
# data: λ_t = mult × γ × mean(diag Σ), keeping the penalty commensurate with
# the risk term regardless of market regime.
TURNOVER_PENALTY_MULT: float = 1.0

# Rebalance-frequency slider tiers → scheduled re-optimization cadence (hours).
# Hourly is the hard cap: quantum jobs cost real money (mirrors strategy.ts).
REBALANCE_TIERS_HOURS: tuple[int, ...] = (24, 8, 4, 2, 1)

# -----------------------------------------------------------------------------
# QUBO encoding hyperparameters
# -----------------------------------------------------------------------------

BIT_PRECISION: int = 4  # b — 16 levels per asset across [w_min, w_max]
PENALTY_MULT_BUDGET: float = 10.0  # λ_sum = mult × max QUBO objective coefficient

# A QUBO solver's weights live on a discrete grid, so Σw=1 is only achievable
# to within ~half a grid step. Decoded weights within this tolerance of 1 are
# normalized onto the simplex before the feasibility gate.
QUBO_NORMALIZE_TOL: float = 0.05

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
# SA (CPU) vs D-Wave (QPU).
GUROBI_IN_RACE: bool = True

# -----------------------------------------------------------------------------
# D-Wave (joins the race only when DWAVE_API_TOKEN is set)
# -----------------------------------------------------------------------------

DWAVE_NUM_READS: int = 100  # anneal samples per solve — tune against QPU budget

# -----------------------------------------------------------------------------
# Solver deadlines (seconds)
# -----------------------------------------------------------------------------

SOLVER_DEADLINE_S: float = 2.0  # per-solver wall-clock budget
RACE_OVERALL_DEADLINE_S: float = 3.0  # outer cap on the parallel race

# -----------------------------------------------------------------------------
# MTM tick cadence (seconds)
# -----------------------------------------------------------------------------

MTM_TICK_S: float = 3.0
SIGMA_REFRESH_S: float = 1800.0  # covariance window refresh cadence (30 min)

# -----------------------------------------------------------------------------
# Market data source
# -----------------------------------------------------------------------------

# "synthetic" → deterministic stand-in (no network);
# "assets-api" → the local assets-api price-indexing service (REST, SQLite-backed).
MARKET_DATA_SOURCE: str = "synthetic"
SYNTHETIC_SEED: int = 20260625  # booth day — deterministic synthetic history
ASSETS_API_BASE_URL: str = "http://127.0.0.1:8080"  # assets-api service
ASSETS_API_TIMEOUT_S: float = 10.0

# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------

# Origins allowed by CORS. The deployed MVP plus local dev.
CORS_ORIGINS: tuple[str, ...] = (
    "https://qtw-tradinggame.netlify.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
QR_BASE_URL: str = "https://qtw-tradinggame.netlify.app"  # /p/{agentId} deep link base
