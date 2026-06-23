"""WebSocket endpoints — the live push channels.

`WS /agents/{id}` streams per-agent AgentUpdates (subscribeAgent). `WS /tv/events`
streams booth-wide events (new-agent splash → TV State D, rank reshuffles). Both
just drain a bus subscription queue to the socket; the MTM scheduler and the
optimize handler are the publishers.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import config
from ..events import feeds
from ..events.bus import get_bus
from ..persistence.agents import get_agent_store
from .auth import token_matches

router = APIRouter()


async def _pump(websocket: WebSocket, channel: str) -> None:
    """Forward everything published on ``channel`` to the socket until it closes."""
    bus = get_bus()
    await websocket.accept()
    queue = bus.subscribe(channel)
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        # Send on a closed socket (client vanished) — drop and clean up.
        pass
    finally:
        bus.unsubscribe(channel, queue)


def _origin_ok(websocket: WebSocket) -> bool:
    # Browsers always send Origin; a malicious cross-site page would send its own
    # (disallowed) origin. Non-browser clients (no Origin header) aren't the CSRF
    # threat. CORS middleware does NOT cover WebSockets, so this is the only guard.
    origin = websocket.headers.get("origin")
    return origin is None or origin in config.CORS_ORIGINS


@router.websocket("/agents/{agent_id}")
async def agent_updates(websocket: WebSocket, agent_id: str) -> None:
    # Owner-token auth (token in the ?t= query param — browsers can't set WS headers).
    record = get_agent_store().get(agent_id)
    token = websocket.query_params.get("t")
    if not _origin_ok(websocket) or record is None or not token_matches(token, record.token_hash):
        await websocket.close(code=1008)  # policy violation — reject before accept
        return
    await _pump(websocket, feeds.agent_channel(agent_id))


@router.websocket("/tv/events")
async def tv_events(websocket: WebSocket) -> None:
    if not _origin_ok(websocket):
        await websocket.close(code=1008)
        return
    await _pump(websocket, feeds.TV_CHANNEL)
