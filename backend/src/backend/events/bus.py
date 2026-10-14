"""In-process async pub/sub event bus.

Backs the live push channels: per-agent MTM updates (`agent:{id}`) and TV events
(`tv`). Each subscriber gets its own `asyncio.Queue`; `publish` is non-blocking
and drops to a full queue (a slow consumer just misses a tick — the next MTM
update supersedes it).

V0 is single-process and in-memory. Fan-out across processes (multiple uvicorn
workers) would need Redis pub/sub or Postgres LISTEN/NOTIFY here — see
docs/TODO.md.
The queues are only touched on the server event loop, so they stay loop-safe without
extra locking. Worker threads (the Quip order worker) publish through
`publish_threadsafe`, which hands the publish to the loop the server bound at startup.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        """Set (or clear, with None) the loop that `publish_threadsafe` publishes on."""
        self._loop = loop

    def publish_threadsafe(self, channel: str, payload: object) -> None:
        """Publish from a thread other than the loop's. Dropped when no loop is bound or
        the loop has closed, as a publish with no subscribers would be."""
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self.publish, channel, payload)
        except RuntimeError:
            pass  # the loop closed during shutdown

    def publish(self, channel: str, payload: object) -> None:
        for queue in tuple(self._subscribers.get(channel, ())):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass  # slow consumer; drop — the next update supersedes this one

    def subscribe(self, channel: str, maxsize: int = 128) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers[channel].add(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(channel)
        if subscribers:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(channel, None)


_bus = EventBus()


def get_bus() -> EventBus:
    """Return the process-wide event bus singleton."""
    return _bus
