"""FastAPI application entrypoint for the MeetStream bridge server.

Run with: `uvicorn app.main:app --reload` (see docs/DEVELOPMENT.md).

This module wires together the pieces defined elsewhere -- it deliberately
contains no MeetStream-specific logic itself. Its two jobs are:
  1. Own the single, connection-pooled `MeetStreamClient` for the process's
     lifetime (via FastAPI's `lifespan`), rather than one per request.
  2. Register one exception handler per `MeetStreamBridgeError` subclass so
     every route gets the same consistent, sanitized JSON error shape without
     each route handler needing its own try/except.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import bots, meetings, transcripts
from app.clients.meetstream import MeetStreamClient
from app.config import get_settings
from app.exceptions import MeetStreamBridgeError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.meetstream_client = MeetStreamClient(
        api_key=settings.meetstream_api_key,
        base_url=settings.meetstream_base_url,
        timeout_seconds=settings.meetstream_request_timeout_seconds,
    )
    logger.info("MeetStream bridge starting up (base_url=%s)", settings.meetstream_base_url)
    try:
        yield
    finally:
        await app.state.meetstream_client.aclose()


app = FastAPI(
    title="MeetStream Bridge",
    description="Normalized HTTP adapter over the MeetStream API, shared by langchain-meetstream and llama-index-meetstream.",
    lifespan=lifespan,
)

app.include_router(bots.router)
app.include_router(meetings.router)
app.include_router(transcripts.router)


@app.exception_handler(MeetStreamBridgeError)
async def handle_bridge_error(request: Request, exc: MeetStreamBridgeError) -> JSONResponse:
    """Maps every bridge exception to `{"error": {"code", "message"}}`.

    This is the one place a `MeetStreamBridgeError` becomes an HTTP response --
    individual routes/services just raise and let this handler translate.
    Never includes exception tracebacks, MeetStream's raw response body, or
    the configured API key in the response.
    """
    logger.warning("%s %s -> %s: %s", request.method, request.url.path, exc.code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness check. Deliberately does not call MeetStream -- this reports
    whether the bridge process itself is up, not whether MeetStream is
    reachable (a MeetStream outage shouldn't make this bridge's own
    orchestration/load-balancer think the bridge itself is unhealthy)."""
    return {"status": "ok"}
