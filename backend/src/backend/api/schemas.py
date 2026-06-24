"""Pydantic schemas mirroring mvp/src/api/types.ts.

Field aliases preserve the camelCase JSON wire format expected by the frontend
while keeping Python attributes snake_case.
"""

from __future__ import annotations

import re
from email.utils import parseaddr
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Universe tickers are ≤6 chars; cap each list item and the list length so an oversized payload
# can't reach validate_basket / persistence (resource-exhaustion guard). 64 tolerates duplicates
# above the 28-asset universe (dedup happens in validate_basket).
_Ticker = Annotated[str, Field(max_length=12)]
_EMAIL_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _valid_email(value: str | None) -> str | None:
    if value is None:
        return None
    email = value.strip()
    if not email:
        raise ValueError("email is required when provided")
    if _EMAIL_CONTROL_RE.search(email) or any(ch.isspace() for ch in email):
        raise ValueError("email contains invalid whitespace or control characters")
    _, parsed = parseaddr(email)
    if parsed != email:
        raise ValueError("email must be a single address")
    local, sep, domain = parsed.rpartition("@")
    if not sep or not local or not domain:
        raise ValueError("email must include local and domain parts")
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("email domain must include a dotted host")
    if any(not part for part in domain.split(".")):
        raise ValueError("email domain contains an empty label")
    return email


class SliderValues(BaseModel):
    """The three strategy sliders, all 0–100 from the UI.

    rebalance_frequency — how often the agent dispatches a scheduled
        re-optimization job (Off → 30m).
    risk_preference — risk-aversion term γ in the objective.
    max_position_size — per-asset weight cap, relative to the basket
        (equal weight 1/n → ~50% in a single asset).
    hold_count — cardinality only: how many of the basket the optimizer holds (K).
        Absolute count, clamped to [3, basket size] at map time. None ⇒ hold all.
        Floored at 3: K=2 on the integer grid forces a degenerate 50/50 split.
    """

    rebalance_frequency: float = Field(ge=0, le=100, alias="rebalanceFrequency")
    risk_preference: float = Field(ge=0, le=100, alias="riskPreference")
    max_position_size: float = Field(ge=0, le=100, alias="maxPositionSize")
    hold_count: int | None = Field(default=None, ge=3, le=100, alias="holdCount")

    model_config = ConfigDict(populate_by_name=True)


class QpuBudgetStatus(BaseModel):
    used: int
    limit: int
    window_seconds: int = Field(alias="windowSeconds")
    retry_after_seconds: int = Field(alias="retryAfterSeconds")
    next_available_at: str | None = Field(default=None, alias="nextAvailableAt")

    model_config = ConfigDict(populate_by_name=True)


class AgentConfig(BaseModel):
    name: str = Field(max_length=80)
    handle: str | None = Field(default=None, max_length=40)  # auto-derived from the name
    email: str | None = Field(default=None, max_length=254)  # required at sign-up (RFC max)
    reach_out: list[str] | None = Field(default=None, max_length=20, alias="reachOut")
    updates_opt_in: bool | None = Field(default=None, alias="updatesOptIn")
    # Cadence for portfolio-result emails: 'daily' | 'hourly' (see notifications
    # scaffold). Only meaningful when updates_opt_in is true.
    update_frequency: str | None = Field(default=None, max_length=16, alias="updateFrequency")
    sliders: SliderValues
    # The player's selected basket — a subset of the 28-asset universe.
    # None/empty falls back to the full universe; re-selectable on retune.
    assets: list[_Ticker] | None = Field(default=None, max_length=64)
    last_solved_at: str | None = Field(default=None, alias="lastSolvedAt")
    next_rebalance_at: str | None = Field(default=None, alias="nextRebalanceAt")
    rebalance_interval_hours: float | None = Field(default=None, alias="rebalanceIntervalHours")
    qpu_budget: QpuBudgetStatus | None = Field(default=None, alias="qpuBudget")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return _valid_email(value)


ProviderType = Literal["QPU", "CPU"]


class PortfolioEntry(BaseModel):
    ticker: str
    pct: float  # 0–100, w_i × 100
    usd: float  # holdings value in USD


class SolverResult(BaseModel):
    provider: str
    provider_type: ProviderType = Field(alias="providerType")
    status: Literal["winner", "feasible", "infeasible", "failed", "timeout"]
    feasible: bool
    solve_time: float | None = Field(default=None, alias="solveTime")
    race_time: float | None = Field(default=None, alias="raceTime")
    objective: float | None = None
    # True for the feasible solver with the best (lowest) objective — the quality
    # leader, which may differ from the speed winner (status="winner").
    best_objective: bool = Field(default=False, alias="bestObjective")
    error: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class HoldingUpdate(BaseModel):
    ticker: str
    units: float
    spot: float
    usd: float
    pct: float


class RoutingResult(BaseModel):
    """Returned from POST /agents/{id}/optimize."""

    provider: str  # 'dwave' | 'sa' | 'gurobi'
    provider_type: ProviderType = Field(alias="providerType")
    solve_time: float = Field(alias="solveTime")  # seconds (winning solver)
    vs_classical: float = Field(alias="vsClassical")  # legacy multiplier for older clients
    portfolio: list[PortfolioEntry]
    solver_results: list[SolverResult] = Field(default_factory=list, alias="solverResults")
    # How the winner won, so the UI shows a genuine tie instead of a noise-level "X% faster":
    # "quality" (better portfolio) | "speed" (objective tie, faster) | "tie" (objective + speed tie).
    outcome: Literal["quality", "speed", "tie"] = "quality"

    # Extensions beyond the mock contract
    kind: Literal["first", "retune"] | None = None
    job_id: str | None = Field(default=None, alias="jobId")
    solved_at: str | None = Field(default=None, alias="solvedAt")  # ISO-8601 UTC
    next_rebalance_at: str | None = Field(default=None, alias="nextRebalanceAt")
    rebalance_interval_hours: float | None = Field(default=None, alias="rebalanceIntervalHours")
    qpu_budget: QpuBudgetStatus | None = Field(default=None, alias="qpuBudget")

    model_config = ConfigDict(populate_by_name=True)


class LeaderboardEntry(BaseModel):
    rank: int
    agent_id: str = Field(alias="agentId")
    name: str
    handle: str | None = None
    total: float  # bankroll + plUSD
    pl_usd: float = Field(alias="plUSD")
    pl_pct: float = Field(alias="plPct")
    jobs_solved: int = Field(alias="jobsSolved")
    primary_provider: ProviderType = Field(alias="primaryProvider")

    model_config = ConfigDict(populate_by_name=True)


class ValuationHistoryPoint(BaseModel):
    total: float
    pl_usd: float = Field(alias="plUSD")
    pl_pct: float = Field(alias="plPct")
    as_of: str | None = Field(default=None, alias="asOf")
    stale: bool = False

    model_config = ConfigDict(populate_by_name=True)


class RoutingProviderStat(BaseModel):
    provider: str
    provider_type: ProviderType = Field(alias="providerType")
    count: int
    pct: float

    model_config = ConfigDict(populate_by_name=True)


class RecentRouting(BaseModel):
    """One solved routing for the TV "recent routings" feed (newest first)."""

    provider: str  # raw key: 'dwave' | 'sa' | 'gurobi' (frontend maps to label)
    provider_type: ProviderType = Field(alias="providerType")  # 'QPU' | 'CPU'
    solve_time: float = Field(alias="solveTime")  # winner seconds
    vs_time: float | None = Field(default=None, alias="vsTime")  # runner-up seconds
    solved_at: str = Field(alias="solvedAt")  # ISO-8601 UTC

    model_config = ConfigDict(populate_by_name=True)


class RoutingStats(BaseModel):
    total: int
    qpu_wins: int = Field(alias="qpuWins")
    cpu_wins: int = Field(alias="cpuWins")
    qpu_pct: float = Field(alias="qpuPct")
    cpu_pct: float = Field(alias="cpuPct")
    providers: list[RoutingProviderStat]
    recent: list[RecentRouting] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class AgentUpdate(BaseModel):
    """Pushed over WS by the MTM loop."""

    pl_usd: float = Field(alias="plUSD")
    pl_pct: float = Field(alias="plPct")
    total: float
    as_of: str | None = Field(default=None, alias="asOf")
    stale: bool = False
    holdings: list[HoldingUpdate] = Field(default_factory=list)
    next_rebalance_at: str | None = Field(default=None, alias="nextRebalanceAt")
    rebalance_interval_hours: float | None = Field(default=None, alias="rebalanceIntervalHours")
    qpu_budget: QpuBudgetStatus | None = Field(default=None, alias="qpuBudget")

    model_config = ConfigDict(populate_by_name=True)


# -----------------------------------------------------------------------------
# Request payloads
# -----------------------------------------------------------------------------


class SubmitAgentResponse(BaseModel):
    agent_id: str = Field(alias="agentId")
    qr_url: str = Field(alias="qrUrl")
    bankroll: float  # surfaced server-side per Q8
    token: str  # capability token — returned once; client stores it, sends as Bearer

    model_config = ConfigDict(populate_by_name=True)


class OptimizeRequest(BaseModel):
    """POST /agents/{id}/optimize.

    Optional `sliders` and `assets` update + optimize in one atomic round-trip.
    A retune liquidates all holdings and reallocates over the new basket.
    """

    sliders: SliderValues | None = None
    assets: list[_Ticker] | None = Field(default=None, max_length=64)


class AgentPatch(BaseModel):
    """PATCH /agents/{id}: persist profile edits without launching a solve."""

    sliders: SliderValues | None = None
    assets: list[_Ticker] | None = Field(default=None, max_length=64)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app_env: str = Field(alias="appEnv")
    persistence: Literal["memory", "sql"]
    market_data_source: str = Field(alias="marketDataSource")
    assets_api_base_url: str = Field(alias="assetsApiBaseUrl")
    qpu_configured: bool = Field(alias="qpuConfigured")
    gurobi_in_race: bool = Field(alias="gurobiInRace")

    model_config = ConfigDict(populate_by_name=True)
