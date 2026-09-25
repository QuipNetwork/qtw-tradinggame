"""Static configuration constants.

Single source of truth for all magic numbers — bankroll, slider ranges,
estimation windows, QUBO hyperparameters, solver deadlines.
"""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# -----------------------------------------------------------------------------
# Bankroll and basket
# -----------------------------------------------------------------------------

BANKROLL_USD: float = 10_000.0
# Smallest basket accepted by the booth UI/API. The K slider then sub-selects a
# smaller support from this watchlist.
MIN_BASKET_SIZE: int = 15

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
# always 100%. 0.85 (was 0.5) lets a speculative book concentrate into its best
# names — the select-encoding weights are a free convex-QP box, so the only hard
# bound is feasibility (K·w_max ≥ 1). Keep mvp/src/utils/strategy.ts in sync.
W_MAX_CEILING: float = 0.85

# Participation floor, not user-facing: w_min = MIN_POSITION_FRACTION/n, so
# every basket asset the player picked shows up in the portfolio. n·w_min ≤ 1
# always holds since MIN_POSITION_FRACTION ≤ 1.
MIN_POSITION_FRACTION: float = 0.25

# Rebalance-frequency slider tiers → scheduled re-optimization cadence (hours).
# None = Off; 0.5 = 30m. The QPU token bucket remains the admission guard.
REBALANCE_TIERS_HOURS: tuple[float | None, ...] = (None, 12.0, 8.0, 4.0, 2.0, 1.0, 0.5)

# -----------------------------------------------------------------------------
# QUBO encoding hyperparameters
# -----------------------------------------------------------------------------

# Bits per asset across [w_min, w_max]. Large baskets drop to 2 bits: QPU feasibility
# is governed by variable count, not bit depth, so halving the variables claws back
# feasible reads (b=3 is dominated by b=2 → skip it). Coarser grid (4 levels) is
# absorbed by simplex normalization. Sweep numbers in CLAUDE.md.
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
# Optimization mode — which problem the race solves
# -----------------------------------------------------------------------------

# "cardinality" (default): cardinality-constrained, semi-continuous MIQP — the
# optimizer sub-selects exactly K of the player's basket and weights them on an
# integer-unit grid (genuinely non-convex; the QPU has structure to exploit).
# "convex": the original mean-variance box-QP fallback (every basket asset held).
OPTIMIZATION_MODE: str = os.environ.get("OPTIMIZATION_MODE", "cardinality").lower()

# cardinality integer-unit grid: weights live on M units, w_i = u_i/M, so the budget
# Σu=M is exactly representable (no normalize crutch). The layout costs n·(1+b)
# variables with b = log2(M)−1 (u_min=1, grid [1/M, 0.5]). M is NOT fixed — it's the
# smallest power of two that fits K (M ≥ K units for K held), clamped to [MIN, MAX]:
# small K → small M → fewer vars → QPU-feasible. See qubo_encoder.units_for_cardinality.
CARDINALITY_MIN_UNITS: int = 8  # floor (b=2, 4 weight levels) — granularity vs feasibility
CARDINALITY_MAX_UNITS: int = 32  # cap (b=4) — M ≥ K so this also caps K at 32 ≥ universe
CARDINALITY_U_MIN: int = 1
# SELECT-encoding only: the weights come from the convex QP, not the integer grid, so the
# participation floor w_min is a free design choice rather than u_min/M. Scale it so the K floors
# collectively lock at most this fraction of the bankroll (w_min = min(u_min/M, this/K)), keeping
# ≥ (1 − this) of the weight free for the QP to tilt — otherwise at large K every held asset is
# pinned at the fixed grid floor (K·w_min → 1) and risk/return sliders stop mattering.
CARDINALITY_FLOOR_BUDGET: float = 0.5
# Size-aware grid budget. Like the convex QUBO_PREFERRED_MAX_VARS, the grid M is raised
# toward a FINER resolution (more weight levels ≈ closer to continuous) for SMALL baskets
# that stay embeddable, and kept COARSE (b=2) for large baskets so the dense QUBO still
# embeds. Pick the largest M with vars = N·log2(M) ≤ this (then floor at M ≥ K). At 72:
# b=4 (16 levels) up to ~14 assets, b=3 to ~18, b=2 above. See units_for_grid.
CARDINALITY_PREFERRED_MAX_VARS: int = 72
# Cardinality / linking penalty peak-coefficient ratios, normalized like
# PENALTY_MULT_BUDGET (which the budget term reuses). See encode_penalized.
CARDINALITY_PENALTY_MULT_CARD: float = 12.0
CARDINALITY_PENALTY_MULT_LINK: float = 12.0
# Diversification / "frustration" reward (β). Adds β·Σ_{i<j} ρ_ij·x_i x_j to the objective —
# penalizes co-selecting correlated assets, making the SELECTION landscape rugged (competing
# pairwise pulls → many local minima) so D-Wave can out-search SA on portfolio quality. For the
# SELECT encoding this value is a FRACTION of the per-problem objective scale (resolve_frustration_beta
# scales it per basket, so the relative pressure is basket-invariant); it applies only to the select
# encoding. 0 = off. This is the PEAK fraction, reached at the full universe — β is RAMPED by basket
# size (below) from a FLOOR at the minimum basket up to this peak. See qpu-c2-beta-findings.md.
CARDINALITY_FRUSTRATION_BETA: float = float(os.environ.get("CARDINALITY_FRUSTRATION_BETA", 0.4))
# N-aware β ramp: OFF below N_MIN, then a FLOOR fraction (CARDINALITY_BETA_FLOOR) at N_MIN rising
# linearly to the full CARDINALITY_FRUSTRATION_BETA at/above N_FULL (the booth universe, 28). N_MIN is
# now the booth-minimum basket (15) and the floor is NON-ZERO because at N=15 a β-fraction of ~0.3 is
# where (a) D-Wave starts beating SA on portfolio quality (the rugged edge emerges; β≤0.2 is a smooth
# tie) AND (b) OOS Sharpe still beats plain MV — both verified 2026-06-23 (Yahoo OOS, 82 windows + a
# live N=15 QPU sweep; see qpu-beta-oos-booth-yahoo / qpu-c2-beta-findings). Below N_MIN β stays 0
# (tiny baskets over-penalize OOS) — moot in play since the minimum basket is 15. Raise N_FULL if the
# universe grows past 28 so larger baskets aren't over-rugged.
CARDINALITY_BETA_FLOOR: float = float(os.environ.get("CARDINALITY_BETA_FLOOR", 0.3))
CARDINALITY_BETA_N_MIN: int = int(os.environ.get("CARDINALITY_BETA_N_MIN", 15))
CARDINALITY_BETA_N_FULL: int = int(os.environ.get("CARDINALITY_BETA_N_FULL", 28))

# cardinality QUBO encoding:
#   "select" (C2, DEFAULT): penalty-free SELECTION-ONLY QUBO (one bit/asset, objective + β only).
#     The greedy projector enforces exactly-K and a convex QP (financial.weighting) sets the
#     weights — both classical — so EVERY read is feasible and D-Wave is no longer handicapped.
#     With CARDINALITY_FRUSTRATION_BETA > 0 (rugged landscape) D-Wave beats SA on portfolio quality.
#     See qpu-c2-beta-findings.md.
#   "penalized" (legacy): integer-units selection QUBO with budget+cardinality+linking penalties
#     (weights solved on the QPU; ~10% feasible at scale → the QPU is handicapped).
CARDINALITY_ENCODING: str = os.environ.get("CARDINALITY_ENCODING", "select").lower()

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

# How the race picks the WINNER:
#   "objective" (default): the best feasible PORTFOLIO (lowest objective), tie-broken by speed
#     within RACE_WINNER_OBJECTIVE_TOL — equal-quality solvers fall back to fastest, but a
#     materially better portfolio wins regardless of speed (so the booth shows "the quantum
#     computer found the best portfolio", with time reported alongside).
#   "speed": legacy fastest-feasible.
RACE_WINNER_BY: str = os.environ.get("RACE_WINNER_BY", "objective").lower()
# Relative tolerance for the objective tie-break: solvers within this fraction of the best
# objective are a quality tie and ranked by speed (β=0 → both optimal → faster wins; a β>0
# quality gap of ~1%+ → the better portfolio wins).
RACE_WINNER_OBJECTIVE_TOL: float = float(os.environ.get("RACE_WINNER_OBJECTIVE_TOL", 0.005))
# Relative time tolerance for the WINNER-DISPLAY tie-break. On a quality tie (objectives within
# RACE_WINNER_OBJECTIVE_TOL) the faster solver is still picked for the portfolio, but the race OUTCOME
# is reported as a genuine TIE when the two solve times are within this fraction of each other — so the
# booth doesn't manufacture an "X% faster" winner from sub-noise timing (SA's ~20-30ms jitter vs the
# QPU's ~constant access time). Beyond this gap the faster solver is a real speed win. A materially
# better objective is always a QUALITY win regardless of time.
RACE_TIME_TIE_TOL: float = float(os.environ.get("RACE_TIME_TIE_TOL", 0.15))

# Explicit experimental xquad route. The Quip chain is slower than the 10 s
# direct-QPU race, so a Quip-enabled race waits long enough for its SDK timeout.
XQUAD_TIMEOUT_S: float = float(os.environ.get("XQUAD_TIMEOUT_S", 120))
QUIP_RPC_URL: str = os.environ.get("QUIP_RPC_URL", "wss://bootnode-1.aglais.quip.network:20049/rpc")
# The faucet belongs to the RPC's chain: the Aglais faucet is the default only
# alongside the default Aglais RPC; a custom QUIP_RPC_URL uses QUIP_FAUCET_URL or none.
QUIP_FAUCET_URL: str | None = (
    os.environ.get("QUIP_FAUCET_URL")
    if "QUIP_RPC_URL" in os.environ
    else "https://faucet.aglais.quip.network"
)

# -----------------------------------------------------------------------------
# D-Wave (joins the race only when DWAVE_API_TOKEN is set)
# -----------------------------------------------------------------------------

# All knobs are env-overridable for tuning sweeps, e.g.
#   DWAVE_CHAIN_STRENGTH_PREFACTOR=4 qtw verify-dwave
DWAVE_NUM_READS: int = int(os.environ.get("DWAVE_NUM_READS", 500))  # fallback / verify-dwave
# Anneal time. The 2026-06-20 real-data sweep showed BOTH feasibility and objective
# quality are flat across 20–500µs; longer anneal slightly REDUCES feasibility and costs
# 2–3× more QPU access time. So use the short end — faster, no quality cost.
DWAVE_ANNEAL_TIME_US: int = int(os.environ.get("DWAVE_ANNEAL_TIME_US", 20))

# num_reads scaled to QUBO size, FLOORED at 500 to match SA's baseline (apples-to-apples
# at both ends — D-Wave and SA draw the same minimum). Large baskets get more reads to
# catch a rare feasible sample (feasible-reads scale ~linearly); capped at 1000. One QPU
# job, so wall-clock stays cheap. Tiers: (max_vars_inclusive, num_reads), first match.
DWAVE_READS_BY_VARS: tuple[tuple[int, int], ...] = (
    (48, 500),
    (72, 600),
    (10**9, 1000),
)
# Spin-reversal transforms (gauge averaging, ~1.35× feasibility via ICE cancellation).
# DISABLED in the race: the only API is the client-side composite, which runs each gauge
# as a separate cloud job → blows the wall-clock deadline. Plumbing (srt_for_vars,
# _get_srt_sampler) kept for offline use. Tiers: (max_vars, n_transforms).
DWAVE_SRT_BY_VARS: tuple[tuple[int, int], ...] = ((10**9, 0),)
# Chain strength = uniform torque compensation × this prefactor. Raise if
# verify-dwave reports chain breaks above ~5% (long chains need stronger bonds).
# ×3 from hardware sweeps: ×2 leaves ~17% chain breaks at 75+ vars; ×3 gives
# 0.4% there with margin to spare at small baskets.
DWAVE_CHAIN_STRENGTH_PREFACTOR: float = float(os.environ.get("DWAVE_CHAIN_STRENGTH_PREFACTOR", 3.0))
# Optional solver topology constraint ("pegasus" | "zephyr"); empty → Leap's default
# (lets the more-connected Advantage2/Zephyr be selected as it matures). A knob for
# experiments, not a hard pin.
DWAVE_SOLVER_TOPOLOGY: str = os.environ.get("DWAVE_SOLVER_TOPOLOGY", "")

# Per-agent QPU admission budget. Limits optimization attempts that include
# D-Wave in the race; CPU-only runs are unaffected. QPU access is ~0.13–0.3 s per
# solve, so one hour of QPU time covers booth retunes comfortably (~12k–27k solves)
# — this cap is the per-agent retune cooldown / anti-spam knob, NOT a booth-wide
# budget gate. Set to 8 / 10 min (a retune ≈ every 75 s) now that the cost is known.
QPU_BUDGET_MAX_ATTEMPTS: int = int(os.environ.get("QPU_BUDGET_MAX_ATTEMPTS", 8))
QPU_BUDGET_WINDOW_S: int = int(os.environ.get("QPU_BUDGET_WINDOW_S", 600))

# Anti-abuse rate limit on agent creation (POST /agents). In-memory + process-local
# (single-worker deploy). Bounds a scripted flood of fresh agents (each grants a new
# QPU budget) via a per-IP cap and a booth-wide hourly ceiling.
# SIGNUP_RATE_PER_IP=0 DISABLES the per-IP cap (the default): a packed conference shares
# one NAT IP, so per-IP would throttle the whole venue, not abuse. The hourly ceiling +
# one-agent-per-email + per-agent QPU budget remain as the real guards.
SIGNUP_RATE_PER_IP: int = int(os.environ.get("SIGNUP_RATE_PER_IP", 0))
SIGNUP_RATE_WINDOW_S: int = int(os.environ.get("SIGNUP_RATE_WINDOW_S", 600))
SIGNUP_RATE_GLOBAL_PER_HOUR: int = int(os.environ.get("SIGNUP_RATE_GLOBAL_PER_HOUR", 300))

# Booth-kiosk gate. When set, POST /agents requires a matching X-Kiosk-Key header so
# signup stays off the public web (a returning attendee can't mint a second agent from
# their phone). A valid kiosk key is also trusted — it skips the per-IP signup limit, so
# the single booth-tablet IP (and shared conference WiFi) is never throttled. Unset → no
# gate, normal per-IP limiting (dev/tests).
KIOSK_SIGNUP_KEY: str = os.environ.get("KIOSK_SIGNUP_KEY", "")

# Admin dashboard gate. When set, the /admin/* endpoints require a matching
# X-Admin-Key header (the operator dashboard reads every attendee's email and can
# hide/disable agents). Unset → admin endpoints are disabled (403). Backend-only
# secret; lives in /opt/qtw/backend.env, never in Netlify/browser env.
ADMIN_API_KEY: str = os.environ.get("ADMIN_API_KEY", "")

# -----------------------------------------------------------------------------
# Solver deadlines (seconds)
# -----------------------------------------------------------------------------

SOLVER_DEADLINE_S: float = 10.0  # per-solver wall-clock budget (also Gurobi TimeLimit)
RACE_OVERALL_DEADLINE_S: float = 10.0  # outer cap on the parallel race (the binding deadline)
# Headroom raised to 10s: SA now matches D-Wave's read budget (up to 1000 reads) on large
# baskets, and D-Wave wall-clock includes cloud queue+round-trip.

# -----------------------------------------------------------------------------
# MTM tick cadence (seconds). Match assets-api's default SPOT_INTERVAL=10s so
# the backend usually publishes after the spot cache can actually change.
# -----------------------------------------------------------------------------

MTM_TICK_S: float = float(os.environ.get("MTM_TICK_S", 10.0))
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
# Only the real deploy values require DATABASE_URL — the app refuses to start
# in-memory there (data would vanish on restart). Every other value (local,
# local-dev, local-container, local-smoke-*, …) may run in-memory. See
# api/app.py:_check_required_config and docs/DEPLOY.md.
DB_REQUIRED_ENVS: frozenset[str] = frozenset({"production", "booth"})

# Cap on concurrent optimization solves (one process-wide gate; single-worker
# deploy). Bounds worker threads + assets-api / QPU pressure under a retune burst.
SOLVE_CONCURRENCY: int = int(os.environ.get("SOLVE_CONCURRENCY", 4))

# -----------------------------------------------------------------------------
# Email (Resend)
# -----------------------------------------------------------------------------

# Resend transactional email over its HTTPS API (port 443) — the reliable sender
# on the droplet (DigitalOcean blocks outbound SMTP). Backend-only deployment
# secrets; in production they live in `/opt/qtw/backend.env`, never in the
# Netlify/browser env. Email sends only when RESEND_API_KEY is set; EMAIL_FROM
# must be a Resend-verified sender (e.g. "Quip Network <noreply@quip.network>").
RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM: str = os.environ.get("EMAIL_FROM", "")
RESEND_TIMEOUT_S: float = float(os.environ.get("RESEND_TIMEOUT_S", 10.0))

# Kill-switch for the throttled per-rebalance result emails (the opt-in cadence). Set
# RESULT_EMAILS_ENABLED=0 to stop them (e.g. at booth wind-down) while still allowing the
# transactional signup email and the one-shot send-off (see notifications/seeoff.py).
RESULT_EMAILS_ENABLED: bool = _env_bool("RESULT_EMAILS_ENABLED", default=True)

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
