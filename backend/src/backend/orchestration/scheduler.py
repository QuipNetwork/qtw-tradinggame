"""Background schedulers — the MTM loop.

`run_mtm_loop` is an async task started by the API lifespan. Every `MTM_TICK_S`
it revalues every agent's holdings against a fresh spot snapshot, persists the
new valuation, and publishes an AgentUpdate per agent. It never trades — pure
revaluation until the user retunes (CLAUDE.md §5.5). Publishing happens on the
event loop, so the bus queues stay loop-safe.

"""

from __future__ import annotations

import asyncio
import logging
import time

from .. import config
from ..events.bus import EventBus
from ..financial.pnl import mark_to_market
from ..financial.prices.base import MarketDataSource, SpotSnapshot
from ..financial.prices.source import get_source
from ..persistence.agents import AgentStore, get_agent_store


async def run_mtm_loop(
    bus: EventBus,
    stop: asyncio.Event,
    *,
    agents: AgentStore | None = None,
    market: MarketDataSource | None = None,
    tick_s: float | None = None,
) -> None:
    """Revalue holdings and push AgentUpdates until ``stop`` is set."""
    agents = agents if agents is not None else get_agent_store()
    market = market if market is not None else get_source()
    tick = tick_s if tick_s is not None else config.MTM_TICK_S

    log = logging.getLogger(__name__)
    last_error_log = 0.0
    last_snapshot_at: dict[str, float] = {}
    while not stop.is_set():
        try:
            records = agents.all()
            tickers = sorted({t for agent in records for t in agent.holdings_units})
            if tickers:
                snapshot = _spot_snapshot(market, tickers)
                now = time.monotonic()
                for agent in records:
                    if not agent.holdings_units:
                        continue
                    update = mark_to_market(
                        agent.holdings_units,
                        snapshot.prices,
                        agent.bankroll,
                        as_of=snapshot.as_of,
                        stale=snapshot.stale,
                    )
                    agents.set_valuation(agent.id, update)
                    if _snapshot_due(agent.id, now, last_snapshot_at):
                        agents.record_valuation_snapshot(agent.id, update)
                        last_snapshot_at[agent.id] = now
                    bus.publish(f"agent:{agent.id}", update.model_dump(by_alias=True))
        except Exception as exc:
            # A flaky data source must not kill the loop; skip this tick.
            now = time.monotonic()
            if now - last_error_log >= config.MTM_ERROR_LOG_INTERVAL_S:
                log.warning("MTM tick failed; skipping update: %s", exc)
                last_error_log = now
        # Sleep one tick, but wake immediately when asked to stop.
        try:
            await asyncio.wait_for(stop.wait(), timeout=tick)
        except TimeoutError:
            pass


def _spot_snapshot(market: MarketDataSource, tickers: list[str]) -> SpotSnapshot:
    snapshot = getattr(market, "spot_snapshot", None)
    if callable(snapshot):
        return snapshot(tickers)
    return SpotSnapshot(prices=market.spot_prices(tickers))


def _snapshot_due(agent_id: str, now: float, last_snapshot_at: dict[str, float]) -> bool:
    interval = config.VALUATION_SNAPSHOT_INTERVAL_S
    if interval <= 0:
        return False
    return now - last_snapshot_at.get(agent_id, 0.0) >= interval
