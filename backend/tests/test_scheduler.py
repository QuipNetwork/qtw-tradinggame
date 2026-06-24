"""MTM scheduler publishes live valuation updates for active holdings only."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.api.schemas import AgentConfig, QpuBudgetStatus, SliderValues
from backend.events.bus import EventBus
from backend.financial.prices.base import SpotSnapshot
from backend.notifications import email as email_mod
from backend.orchestration import scheduler
from backend.orchestration.scheduler import run_mtm_loop, run_scheduled_rebalance_loop
from backend.persistence.agents import AgentStore
from backend.persistence.qpu_budget import QpuBudgetExceeded


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

    task = asyncio.create_task(run_mtm_loop(bus, stop, agents=agents, market=market, tick_s=60.0))
    payload = await asyncio.wait_for(queue.get(), timeout=1.0)
    stop.set()
    await task

    assert market.requested == ["BTC", "ETH"]
    assert payload["total"] == pytest.approx(11_000.0)
    assert payload["asOf"] == "2026-06-17T12:00:00+00:00"
    assert payload["stale"] is False
    assert payload["nextRebalanceAt"] == agents.get(record.id).next_rebalance_at
    assert payload["rebalanceIntervalHours"] == 4
    assert {h["ticker"] for h in payload["holdings"]} == {"BTC", "ETH"}


@pytest.mark.asyncio
async def test_mtm_loop_isolates_a_failing_agent():
    # A persistently-failing agent (e.g. a bad DB write) must not starve the rest of the tick:
    # the healthy agent still gets its MTM update even though an earlier agent raised.
    class FailOneStore(AgentStore):
        bad_id: str | None = None

        def set_valuation(self, agent_id, update):
            if agent_id == self.bad_id:
                raise RuntimeError("boom")
            super().set_valuation(agent_id, update)

    sliders = SliderValues(rebalanceFrequency=50, riskPreference=70, maxPositionSize=50)
    agents = FailOneStore()
    bad = agents.create(
        AgentConfig(name="Bad", email="b@x.io", sliders=sliders, assets=["BTC", "ETH"]),
        bankroll=10_000.0,
    )
    good = agents.create(
        AgentConfig(name="Good", email="g@x.io", sliders=sliders, assets=["BTC", "ETH"]),
        bankroll=10_000.0,
    )
    for r in (bad, good):
        agents.apply_solve(
            r.id, holdings_units={"BTC": 0.1, "ETH": 1.0}, total=10_000.0, provider_type="CPU"
        )
    agents.bad_id = bad.id  # set after setup so only the MTM tick trips it

    bus = EventBus()
    good_q = bus.subscribe(f"agent:{good.id}")
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_mtm_loop(bus, stop, agents=agents, market=MovingSpot(), tick_s=60.0)
    )
    # `bad` is processed first (insertion order) and raises; `good` must still be published.
    payload = await asyncio.wait_for(good_q.get(), timeout=1.0)
    stop.set()
    await task
    assert payload["total"] == pytest.approx(11_000.0)


@pytest.mark.asyncio
async def test_scheduled_rebalance_loop_runs_due_agent_and_publishes(monkeypatch):
    agents = AgentStore()
    record = agents.create(
        AgentConfig(
            name="Due",
            email="due@example.com",
            sliders=SliderValues(
                rebalanceFrequency=100,
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
        provider_type="QPU",
    )
    record.next_rebalance_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

    def fake_optimization(agent_id, *, agents, jobs, market, source):
        assert source == "scheduled"
        agents.apply_solve(
            agent_id,
            holdings_units={"BTC": 0.11, "ETH": 0.9},
            total=10_250.0,
            provider_type="QPU",
        )
        return SimpleNamespace(
            events=[
                SimpleNamespace(
                    channel=f"agent:{agent_id}",
                    payload={
                        "type": "scheduled-rebalance",
                        "nextRebalanceAt": agents.get(agent_id).next_rebalance_at,
                    },
                )
            ]
        )

    monkeypatch.setattr(scheduler, "run_optimization", fake_optimization)

    bus = EventBus()
    queue = bus.subscribe(f"agent:{record.id}")
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_scheduled_rebalance_loop(
            bus,
            stop,
            agents=agents,
            jobs=SimpleNamespace(),
            market=MovingSpot(),
            tick_s=60.0,
        )
    )
    payload = await asyncio.wait_for(queue.get(), timeout=1.0)
    stop.set()
    await task

    assert payload["type"] == "scheduled-rebalance"
    assert agents.get(record.id).jobs_solved == 2
    assert datetime.fromisoformat(agents.get(record.id).next_rebalance_at) > datetime.now(UTC)


@pytest.mark.asyncio
async def test_scheduled_rebalance_loop_skips_agents_with_cadence_off(monkeypatch):
    agents = AgentStore()
    record = agents.create(
        AgentConfig(
            name="Off",
            email="off@example.com",
            sliders=SliderValues(
                rebalanceFrequency=0,
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
        provider_type="QPU",
    )
    last_solved_at = record.last_solved_at
    called = False

    def fake_optimization(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("off cadence should not schedule optimization")

    monkeypatch.setattr(scheduler, "run_optimization", fake_optimization)

    stop = asyncio.Event()
    task = asyncio.create_task(
        run_scheduled_rebalance_loop(
            EventBus(),
            stop,
            agents=agents,
            jobs=SimpleNamespace(),
            market=MovingSpot(),
            tick_s=0.01,
        )
    )
    await asyncio.sleep(0.03)
    stop.set()
    await task

    updated = agents.get(record.id)
    assert called is False
    assert updated.jobs_solved == 1
    assert updated.last_solved_at == last_solved_at
    assert updated.next_rebalance_at is None
    assert updated.rebalance_interval_hours is None


@pytest.mark.asyncio
async def test_scheduled_rebalance_defers_when_qpu_budget_is_exhausted(monkeypatch):
    agents = AgentStore()
    record = agents.create(
        AgentConfig(
            name="Deferred",
            email="deferred@example.com",
            sliders=SliderValues(
                rebalanceFrequency=100,
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
        provider_type="QPU",
    )
    record.next_rebalance_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    next_available = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    status = QpuBudgetStatus(
        used=3,
        limit=3,
        windowSeconds=600,
        retryAfterSeconds=300,
        nextAvailableAt=next_available,
    )

    def fake_optimization(agent_id, *, agents, jobs, market, source):
        raise QpuBudgetExceeded(status)

    monkeypatch.setattr(scheduler, "run_optimization", fake_optimization)

    bus = EventBus()
    queue = bus.subscribe(f"agent:{record.id}")
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_scheduled_rebalance_loop(
            bus,
            stop,
            agents=agents,
            jobs=SimpleNamespace(),
            market=MovingSpot(),
            tick_s=60.0,
        )
    )
    payload = await asyncio.wait_for(queue.get(), timeout=1.0)
    stop.set()
    await task

    assert agents.get(record.id).jobs_solved == 1
    assert agents.get(record.id).next_rebalance_at == next_available
    assert payload["nextRebalanceAt"] == next_available
    assert payload["qpuBudget"]["retryAfterSeconds"] == 300


@pytest.mark.asyncio
async def test_scheduled_rebalance_sends_throttled_result_email(monkeypatch):
    agents = AgentStore()
    record = agents.create(
        AgentConfig(
            name="Mailer",
            email="mailer@example.com",
            updatesOptIn=True,
            updateFrequency="hourly",
            sliders=SliderValues(rebalanceFrequency=100, riskPreference=70, maxPositionSize=50),
            assets=["BTC", "ETH"],
        ),
        bankroll=10_000.0,
    )
    agents.apply_solve(
        record.id, holdings_units={"BTC": 0.1, "ETH": 1.0}, total=10_000.0, provider_type="QPU"
    )
    record.next_rebalance_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    record.last_update_email_at = None  # force "due"

    def fake_optimization(agent_id, *, agents, jobs, market, source):
        agents.apply_solve(
            agent_id, holdings_units={"BTC": 0.11, "ETH": 0.9}, total=10_250.0, provider_type="QPU"
        )
        return SimpleNamespace(
            events=[
                SimpleNamespace(
                    channel=f"agent:{agent_id}", payload={"type": "scheduled-rebalance"}
                )
            ]
        )

    monkeypatch.setattr(scheduler, "run_optimization", fake_optimization)

    sent: list[str] = []

    class CaptureProvider:
        def send(self, *, to, subject, html, text):
            sent.append(to)

    email_mod.set_email_provider(CaptureProvider())
    bus = EventBus()
    queue = bus.subscribe(f"agent:{record.id}")
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_scheduled_rebalance_loop(
            bus, stop, agents=agents, jobs=SimpleNamespace(), market=MovingSpot(), tick_s=60.0
        )
    )
    try:
        await asyncio.wait_for(queue.get(), timeout=1.0)
        for _ in range(50):  # email dispatches just after the publish
            if sent:
                break
            await asyncio.sleep(0.01)
    finally:
        stop.set()
        await task
        email_mod.set_email_provider(email_mod.NoopEmailProvider())

    assert sent == ["mailer@example.com"]
    assert agents.get(record.id).last_update_email_at is not None
