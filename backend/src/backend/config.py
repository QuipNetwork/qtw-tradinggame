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

SIGMA_WINDOW_HOURS: int = 720  # 30 days × 24h — fixed, not slider-controlled
# μ lookback. Fixed now that the holding-style slider was dropped (the basket
# expresses holding intent); 7 days of hourly returns.
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

# Minimum position as a fraction of equal weight: w_min = MIN_POSITION_FRACTION/n.
# With no cardinality constraint, every basket asset is held at least w_min —
# the player picked it, so it shows up in the portfolio. n·w_min ≤ 1 always
# holds since MIN_POSITION_FRACTION ≤ 1.
MIN_POSITION_FRACTION: float = 0.5

LAMBDA_T_MAX: float = 50.0  # turnover penalty ceiling; V0 is forced to 0

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
# V0 scope toggles
# -----------------------------------------------------------------------------

V0_LAMBDA_T_FORCED_ZERO: bool = True  # Turnover penalty disabled in V0
V0_TRANSACTION_FEE_ENABLED: bool = False  # Explicit fee disabled in V0
TRANSACTION_FEE_RATE: float = 0.003  # c = 0.3% one-way (when enabled in V1)

# -----------------------------------------------------------------------------
# Feasibility tolerances (V0 quality bar)
# -----------------------------------------------------------------------------

EPS_BUDGET: float = 1e-3  # |Σwᵢ − 1| < EPS_BUDGET
EPS_BOX: float = 1e-3  # wᵢ ≤ w_max + EPS_BOX

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
