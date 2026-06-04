"""Channel naming + fan-out helpers over the event bus.

Keeps the channel conventions in one place so the publishers (orchestration job,
MTM scheduler) and the WS handlers agree. ``agent:{id}`` carries per-agent
AgentUpdates; ``tv`` carries booth-wide events (new-agent splash → TV State D,
rank reshuffles).
"""

from __future__ import annotations

import asyncio

from .bus import EventBus

TV_CHANNEL = "tv"


def agent_channel(agent_id: str) -> str:
    return f"agent:{agent_id}"


def subscribe_agent(bus: EventBus, agent_id: str) -> asyncio.Queue:
    return bus.subscribe(agent_channel(agent_id))


def subscribe_tv(bus: EventBus) -> asyncio.Queue:
    return bus.subscribe(TV_CHANNEL)
