"""FastAPI application factory.

Wires the HTTP + WS routers, CORS for the MVP origins, and a lifespan that runs
both background loops: mark-to-market valuation and scheduled rebalances. Run
locally with:

    uvicorn backend.api.app:app --reload --workers 1

Use one worker for the first production deployment because the event bus and
schedulers are process-local.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import config
from ..events.bus import get_bus
from ..orchestration.scheduler import run_mtm_loop, run_scheduled_rebalance_loop
from . import routes, ws
from .ratelimit import SignupRateLimiter

log = logging.getLogger(__name__)


def _check_market_source() -> None:
    """Announce the active data source; a missing assets-api should fail loudly."""
    from ..financial.prices.assets_api import AssetsApiSource
    from ..financial.prices.source import get_source

    source = get_source()
    log.info("market data source: %s", type(source).__name__)
    if isinstance(source, AssetsApiSource):
        try:
            source.health()
            log.info("assets-api reachable at %s", config.ASSETS_API_BASE_URL)
        except Exception as e:
            log.error(
                "assets-api unreachable at %s — solves and MTM will fail until it is up "
                "(or set MARKET_DATA_SOURCE=synthetic): %s",
                config.ASSETS_API_BASE_URL,
                e,
            )


def _check_required_config() -> None:
    """Refuse to boot in-memory for a real deploy (APP_ENV=production/booth) —
    a restart would wipe every agent/job/valuation. All local/dev runs (local,
    local-dev, local-smoke-*, …) keep the in-memory default."""
    if config.APP_ENV.strip().lower() in config.DB_REQUIRED_ENVS and not config.DATABASE_URL:
        raise RuntimeError(
            f"APP_ENV={config.APP_ENV!r} requires DATABASE_URL "
            "(refusing in-memory persistence for a real deploy — data would be lost "
            "on restart). Set DATABASE_URL, or use a local APP_ENV for in-memory."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _check_required_config()
    _check_market_source()
    stop = asyncio.Event()
    bus = get_bus()
    tasks = [
        asyncio.create_task(run_mtm_loop(bus, stop)),
        asyncio.create_task(run_scheduled_rebalance_loop(bus, stop)),
    ]
    try:
        yield
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    # No public API explorer on a real deploy (production/booth); keep it locally.
    docs_on = config.APP_ENV.strip().lower() not in config.DB_REQUIRED_ENVS
    app = FastAPI(
        title="QTW 2026 Trading Game",
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )
    app.state.signup_limiter = SignupRateLimiter()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.CORS_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes.router)
    app.include_router(ws.router)
    return app


app = create_app()
