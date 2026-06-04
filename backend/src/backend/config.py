"""Static configuration constants.

Single source of truth for all magic numbers — bankroll, slider ranges,
estimation windows, QUBO hyperparameters, solver deadlines.
"""

from __future__ import annotations

# -----------------------------------------------------------------------------
# Bankroll and basket
# -----------------------------------------------------------------------------

BANKROLL_USD: float = 10_000.0
N_ASSETS: int = 15

# -----------------------------------------------------------------------------
# Estimation windows (hours)
# -----------------------------------------------------------------------------

SIGMA_WINDOW_HOURS: int = 720  # 30 days × 24h — fixed, not slider-controlled
TAU_RANGE_HOURS: tuple[int, int] = (24, 720)  # Holding Style slider range

# -----------------------------------------------------------------------------
# Slider → param ranges (single source of truth, used by slider_map)
# -----------------------------------------------------------------------------

GAMMA_RANGE: tuple[float, float] = (0.5, 20.0)  # log-scaled
# Per-asset cap. slider_map floors the low end at 1/K so the budget Σwᵢ=1 is
# always reachable (K·w_max ≥ 1) and the diversified end yields equal weights.
W_MAX_HI: float = 0.8
K_RANGE: tuple[int, int] = (3, 12)  # linear, integer
LAMBDA_T_MAX: float = 50.0  # linear, V0 is forced to 0
# Minimum size of a *selected* position, as a fraction of equal weight: the model
# enforces wᵢ ≥ w_min·yᵢ with w_min = MIN_POSITION_FRACTION / K. Combined with
# Σyᵢ = K this turns "at most K" into exactly-K (decision Q1). Must keep
# K·w_min ≤ 1, i.e. MIN_POSITION_FRACTION ≤ 1.
MIN_POSITION_FRACTION: float = 0.5

# -----------------------------------------------------------------------------
# QUBO encoding hyperparameters
# -----------------------------------------------------------------------------

BIT_PRECISION: int = 4  # b — 16 levels per asset, ~6% granularity at w_max=0.5
PENALTY_MULT_BUDGET: float = 10.0  # λ_sum = mult × max QUBO objective coefficient
PENALTY_MULT_CARDINALITY: float = 10.0  # λ_K = mult × max QUBO objective coefficient
COUPLING_MULT: float = 10.0  # M_couple for x ↔ y coupling

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

# "synthetic" → deterministic stand-in (no network); "coingecko" → live (pending).
MARKET_DATA_SOURCE: str = "synthetic"
SYNTHETIC_SEED: int = 20260625  # booth day — deterministic synthetic history

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
