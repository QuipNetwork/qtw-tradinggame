"""MTM scheduler publishes live valuation updates for active holdings only."""

from __future__ import annotations

import asyncio

import pytest

from backend.api.schemas import AgentConfig, SliderValues
from backend.events.bus import EventBus
from backend.financial.prices.base import SpotSnapshot
from backend.orchestration.scheduler import run_mtm_loop
from backend.persistence.agents import AgentStore


class MovingSpot:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def spot_snapshot(self, tickers: list[str]) -> SpotSnapshot:
        self.requested = tickers
        return SpotSnapshot(
            prices={"BTC": 60_000.0, "ETH": 5_000.0},
            as_of="2026-06-17T12:00:00+00:00",
            stale=False,
        )


@pytest.mark.asyncio
async def test_mtm_loop_requests_held_tickers_and_publishes_holdings():
    agents = AgentStore()
    record = agents.create(
        AgentConfig(
            name="Neo",
            email="neo@example.com",
            sliders=SliderValues(
                rebalanceFrequency=50,
                riskPreference=70,
                maxPositionSize=50,
            ),
            assets=["BTC", "ETH"],
        ),
        bankroll=10_000.0,
    )
    agents.apply_solve(
        record.id,
        holdings_units={"BTC": 0.1, "ETH": 1.0},
        total=10_000.0,
        provider_type="CPU",
    )

    bus = EventBus()
    queue = bus.subscribe(f"agent:{record.id}")
    stop = asyncio.Event()
    market = MovingSpot()

    task = asyncio.create_task(
        run_mtm_loop(bus, stop, agents=agents, market=market, tick_s=60.0)
    )
    payload = await asyncio.wait_for(queue.get(), timeout=1.0)
    stop.set()
    await task

    assert market.requested == ["BTC", "ETH"]
    assert payload["total"] == pytest.approx(11_000.0)
    assert payload["asOf"] == "2026-06-17T12:00:00+00:00"
    assert payload["stale"] is False
    assert {h["ticker"] for h in payload["holdings"]} == {"BTC", "ETH"}
