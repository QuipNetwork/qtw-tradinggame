"""WebSocket endpoints — the live push channels.

`WS /agents/{id}` streams per-agent AgentUpdates (subscribeAgent). `WS /tv/events`
streams booth-wide events (new-agent splash → TV State D, rank reshuffles). Both
just drain a bus subscription queue to the socket; the MTM scheduler and the
optimize handler are the publishers.

Browsers can't set headers on a WebSocket, so the agent's owner token travels in
Sec-WebSocket-Protocol: the client offers `quip.v1` and `auth.<token>`, and the
server accepts `quip.v1`. A query string would land in the server log.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import config
from ..events import feeds
from ..events.bus import get_bus
from ..persistence.agents import get_agent_store
from .auth import token_matches

router = APIRouter()

SUBPROTOCOL = "quip.v1"
_AUTH_PREFIX = "auth."


async def _pump(websocket: WebSocket, channel: str, subprotocol: str | None = None) -> None:
    """Forward everything published on ``channel`` to the socket until it closes."""
    bus = get_bus()
    await websocket.accept(subprotocol=subprotocol)
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


def _subprotocol_token(websocket: WebSocket) -> str | None:
    """The token offered as `auth.<token>` beside `quip.v1`, or None."""
    offered = websocket.scope.get("subprotocols") or []
    if SUBPROTOCOL not in offered:
        return None
    tokens = [p.removeprefix(_AUTH_PREFIX) for p in offered if p.startswith(_AUTH_PREFIX)]
    return tokens[0] if len(tokens) == 1 else None


@router.websocket("/agents/{agent_id}")
async def agent_updates(websocket: WebSocket, agent_id: str) -> None:
    record = get_agent_store().get(agent_id)
    token = _subprotocol_token(websocket)
    subprotocol = SUBPROTOCOL if token is not None else None
    if token is None:
        # TODO(QUI-1855): remove the ?t= fallback, and redact_ws_tokens with it, once tabs
        # opened before the subprotocol are gone.
        token = websocket.query_params.get("t")
    if not _origin_ok(websocket) or record is None or not token_matches(token, record.token_hash):
        await websocket.close(code=1008)  # policy violation — reject before accept
        return
    await _pump(websocket, feeds.agent_channel(agent_id), subprotocol=subprotocol)


@router.websocket("/tv/events")
async def tv_events(websocket: WebSocket) -> None:
    if not _origin_ok(websocket):
        await websocket.close(code=1008)
        return
    await _pump(websocket, feeds.TV_CHANNEL)


_TOKEN_QUERY = re.compile(r"([?&]t=)[^&\s\"]+")


class _RedactTokenQuery(logging.Filter):
    """Mask a `t=` query value in uvicorn's log arguments (its WebSocket lines log the
    path with the query string)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _TOKEN_QUERY.sub(r"\1<redacted>", arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


def redact_ws_tokens() -> None:
    """Keep tokens sent through the legacy ?t= fallback out of the server log."""
    for name in ("uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, _RedactTokenQuery) for f in logger.filters):
            logger.addFilter(_RedactTokenQuery())
