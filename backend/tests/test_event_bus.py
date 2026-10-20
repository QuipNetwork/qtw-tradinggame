"""EventBus contract: delivery, drop-on-full (slow-consumer safety), unsubscribe cleanup.

The bus backs every live push channel. Its deliberate drop-on-full behavior keeps a stuck/slow
WebSocket from ever blocking a publisher (the booth must not hang on one bad consumer).
"""

from __future__ import annotations

import asyncio

from backend.events.bus import EventBus


def test_publish_delivers_to_every_subscriber():
    bus = EventBus()
    q1, q2 = bus.subscribe("c"), bus.subscribe("c")
    bus.publish("c", {"x": 1})
    assert q1.get_nowait() == {"x": 1}
    assert q2.get_nowait() == {"x": 1}


def test_publish_to_channel_with_no_subscribers_is_noop():
    EventBus().publish("nobody", {"x": 1})  # must not raise


def test_full_queue_drops_instead_of_blocking():
    # Slow consumer: a full queue drops the new tick rather than blocking the publisher.
    bus = EventBus()
    q = bus.subscribe("c", maxsize=1)
    bus.publish("c", "a")  # fills the queue
    bus.publish("c", "b")  # dropped — no raise, no block
    assert q.get_nowait() == "a"
    assert q.empty()


def test_unsubscribe_removes_queue_and_prunes_empty_channel():
    bus = EventBus()
    q = bus.subscribe("c")
    bus.unsubscribe("c", q)
    assert "c" not in bus._subscribers  # channel pruned when the last subscriber leaves
    bus.publish("c", "x")  # now a no-op, must not raise


def test_unsubscribe_is_idempotent():
    bus = EventBus()
    q = bus.subscribe("c")
    bus.unsubscribe("c", q)
    bus.unsubscribe("c", q)  # second call (e.g. double cleanup) must not raise


def test_one_full_subscriber_does_not_starve_others():
    bus = EventBus()
    slow = bus.subscribe("c", maxsize=1)
    fast = bus.subscribe("c", maxsize=8)
    bus.publish("c", "a")  # fills slow
    bus.publish("c", "b")  # dropped for slow, delivered to fast
    assert fast.get_nowait() == "a"
    assert fast.get_nowait() == "b"
    assert slow.get_nowait() == "a"
    assert slow.empty()


async def test_publish_threadsafe_delivers_from_a_worker_thread():
    bus = EventBus()
    bus.bind_loop(asyncio.get_running_loop())
    q = bus.subscribe("c")
    await asyncio.to_thread(bus.publish_threadsafe, "c", {"x": 1})
    assert await asyncio.wait_for(q.get(), 1.0) == {"x": 1}


def test_publish_threadsafe_without_a_bound_loop_is_noop():
    bus = EventBus()
    q = bus.subscribe("c")
    bus.publish_threadsafe("c", {"x": 1})  # must not raise
    assert q.empty()


def test_publish_threadsafe_after_the_loop_closed_is_noop():
    bus = EventBus()
    loop = asyncio.new_event_loop()
    bus.bind_loop(loop)
    loop.close()
    bus.publish_threadsafe("c", {"x": 1})  # shutdown race: must not raise
