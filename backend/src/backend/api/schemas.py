"""Pydantic schemas mirroring mvp/src/api/types.ts.

Field aliases preserve the camelCase JSON wire format expected by the frontend
while keeping Python attributes snake_case.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SliderValues(BaseModel):
    """All sliders are 0–100 ints from the UI."""

    trading_activity: float = Field(ge=0, le=100, alias="tradingActivity")
    risk_preference: float = Field(ge=0, le=100, alias="riskPreference")
    trade_size: float = Field(ge=0, le=100, alias="tradeSize")
    holding_style: float = Field(ge=0, le=100, alias="holdingStyle")
    diversification: float = Field(ge=0, le=100)

    model_config = ConfigDict(populate_by_name=True)


class AgentConfig(BaseModel):
    name: str
    handle: str | None = None
    sliders: SliderValues


ProviderType = Literal["QPU", "CPU"]


class PortfolioEntry(BaseModel):
    ticker: str
    pct: float  # 0–100, w_i × 100
    usd: float  # holdings value in USD


class RoutingResult(BaseModel):
    """Returned from POST /agents/{id}/optimize."""

    provider: str  # 'dwave' | 'sa' | 'gurobi'
    provider_type: ProviderType = Field(alias="providerType")
    solve_time: float = Field(alias="solveTime")  # seconds (winning solver)
    vs_classical: float = Field(alias="vsClassical")  # winner_time / runner_up_classical_time
    portfolio: list[PortfolioEntry]

    # V1 extensions — optional, present once wired
    kind: Literal["first", "retune"] | None = None
    job_id: str | None = Field(default=None, alias="jobId")
    solved_at: str | None = Field(default=None, alias="solvedAt")  # ISO-8601 UTC
    fee_usd: float | None = Field(default=None, alias="feeUsd")

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


class AgentUpdate(BaseModel):
    """Pushed over WS by the MTM loop."""

    pl_usd: float = Field(alias="plUSD")
    pl_pct: float = Field(alias="plPct")
    total: float

    model_config = ConfigDict(populate_by_name=True)


# -----------------------------------------------------------------------------
# Request payloads
# -----------------------------------------------------------------------------


class SubmitAgentResponse(BaseModel):
    agent_id: str = Field(alias="agentId")
    qr_url: str = Field(alias="qrUrl")
    bankroll: float  # surfaced server-side per Q8

    model_config = ConfigDict(populate_by_name=True)


class OptimizeRequest(BaseModel):
    """POST /agents/{id}/optimize.

    Optional `sliders` payload per Q9 — extending optimize with slider update
    in one atomic round-trip.
    """

    sliders: SliderValues | None = None
