"""Admin dashboard API — operator-only views and controls over every agent.

Gated by ADMIN_API_KEY (X-Admin-Key header). Exposes every attendee's record
(including email) plus two write controls:
  - hidden:   drop an agent from the public leaderboard + TV ranking
  - disabled: cut an agent off from solving (manual retune + scheduled rebalance)

The invariant ``disabled implies hidden`` is enforced here — you can only disable
a hidden agent, and un-hiding clears disabled.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .. import config
from ..persistence.agents import AgentRecord, get_agent_store
from .schemas import SliderValues

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminAgent(BaseModel):
    agent_id: str = Field(alias="agentId")
    name: str
    handle: str | None = None
    email: str | None = None
    rank: int | None = None  # rank on the public board; None when hidden
    total: float
    pl_usd: float = Field(alias="plUSD")
    pl_pct: float = Field(alias="plPct")
    jobs_solved: int = Field(alias="jobsSolved")  # solve count (== retunes)
    primary_provider: str = Field(alias="primaryProvider")
    basket_size: int = Field(alias="basketSize")
    sliders: SliderValues
    created_at: str = Field(alias="createdAt")
    last_solved_at: str | None = Field(default=None, alias="lastSolvedAt")
    hidden: bool
    disabled: bool

    model_config = ConfigDict(populate_by_name=True)


class AdminAgentPatch(BaseModel):
    hidden: bool | None = None
    disabled: bool | None = None


def require_admin(request: Request) -> None:
    """Gate the admin dashboard. 403 when ADMIN_API_KEY is unset (admin disabled)
    or the X-Admin-Key header is missing/incorrect."""
    if not config.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="admin dashboard is disabled")
    provided = request.headers.get("x-admin-key", "")
    if not secrets.compare_digest(provided, config.ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="invalid admin key")


def _to_admin_agent(record: AgentRecord, rank: int | None) -> AdminAgent:
    return AdminAgent(
        agent_id=record.id,
        name=record.name,
        handle=record.handle,
        email=record.email,
        rank=rank,
        total=record.total,
        pl_usd=record.pl_usd,
        pl_pct=record.pl_pct,
        jobs_solved=record.jobs_solved,
        primary_provider=record.primary_provider,
        basket_size=len(record.assets) if record.assets else 0,
        sliders=record.sliders,
        created_at=record.created_at,
        last_solved_at=record.last_solved_at,
        hidden=record.hidden,
        disabled=record.disabled,
    )


def _admin_rows() -> tuple[list[AdminAgent], dict[str, int]]:
    """All agents as admin rows, plus the rank map. Visible agents rank like the
    public board; hidden agents have no rank and sort after the visible ones."""
    records = get_agent_store().all()
    visible = sorted((r for r in records if not r.hidden), key=lambda r: (-r.total, r.id))
    rank_by_id = {r.id: i + 1 for i, r in enumerate(visible)}
    ordered = sorted(records, key=lambda r: (r.hidden, -r.total, r.id))
    return [_to_admin_agent(r, rank_by_id.get(r.id)) for r in ordered], rank_by_id


@router.get("/agents", response_model=list[AdminAgent], dependencies=[Depends(require_admin)])
async def list_agents() -> list[AdminAgent]:
    rows, _ = _admin_rows()
    return rows


@router.patch(
    "/agents/{agent_id}",
    response_model=AdminAgent,
    dependencies=[Depends(require_admin)],
)
async def patch_agent(agent_id: str, body: AdminAgentPatch) -> AdminAgent:
    store = get_agent_store()
    record = store.get(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="agent not found")

    new_hidden = record.hidden if body.hidden is None else body.hidden
    new_disabled = record.disabled if body.disabled is None else body.disabled
    # disabled implies hidden: reject an explicit disable that wouldn't be hidden,
    # and un-hiding always clears disabled (can't be disabled while on the board).
    if body.disabled and not new_hidden:
        raise HTTPException(
            status_code=400, detail="disable requires the agent to be hidden first"
        )
    if not new_hidden:
        new_disabled = False

    store.set_flags(agent_id, hidden=new_hidden, disabled=new_disabled)
    _, rank_by_id = _admin_rows()
    updated = store.get(agent_id)
    assert updated is not None
    return _to_admin_agent(updated, rank_by_id.get(agent_id))
