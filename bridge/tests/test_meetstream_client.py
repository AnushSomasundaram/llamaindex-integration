"""Unit tests for `app/clients/meetstream.py`, independent of the FastAPI app."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.meetstream import MeetStreamClient
from app.exceptions import BotNotFoundError, MeetStreamAuthError, UpstreamError, UpstreamTimeoutError

BASE_URL = "https://api.meetstream.ai/api/v1"


async def test_sends_token_auth_header():
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/bots/bot_1/status").mock(return_value=httpx.Response(200, json={"bot_id": "bot_1", "status": "InMeeting"}))
        client = MeetStreamClient(api_key="secret-key", base_url=BASE_URL)
        try:
            await client.get_bot_status("bot_1")
        finally:
            await client.aclose()

    assert route.calls.last.request.headers["Authorization"] == "Token secret-key"


async def test_retries_on_5xx_then_succeeds():
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/bots/bot_1/status").mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json={"bot_id": "bot_1", "status": "InMeeting"})]
        )
        client = MeetStreamClient(api_key="k", base_url=BASE_URL)
        try:
            result = await client.get_bot_status("bot_1")
        finally:
            await client.aclose()

    assert result["status"] == "InMeeting"
    assert route.call_count == 2


async def test_does_not_retry_create_bot_on_5xx():
    """create_bot must never be retried -- a lost response doesn't mean the
    bot never joined, and duplicating a real bot join is worse than a caller
    needing to retry manually (see the client's own docstring)."""
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/bots/create_bot").mock(return_value=httpx.Response(503))
        client = MeetStreamClient(api_key="k", base_url=BASE_URL)
        try:
            with pytest.raises(UpstreamError):
                await client.create_bot(meeting_url="https://meet.google.com/abc", bot_name="Bot")
        finally:
            await client.aclose()

    assert route.call_count == 1


async def test_maps_401_to_auth_error():
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/bots/bot_1/status").mock(return_value=httpx.Response(401))
        client = MeetStreamClient(api_key="bad-key", base_url=BASE_URL)
        try:
            with pytest.raises(MeetStreamAuthError):
                await client.get_bot_status("bot_1")
        finally:
            await client.aclose()


async def test_maps_404_to_bot_not_found():
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/bots/missing/status").mock(return_value=httpx.Response(404))
        client = MeetStreamClient(api_key="k", base_url=BASE_URL)
        try:
            with pytest.raises(BotNotFoundError):
                await client.get_bot_status("missing")
        finally:
            await client.aclose()


async def test_maps_timeout_to_upstream_timeout_error():
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/bots/bot_1/status").mock(side_effect=httpx.TimeoutException("timed out"))
        client = MeetStreamClient(api_key="k", base_url=BASE_URL)
        try:
            with pytest.raises(UpstreamTimeoutError):
                await client.get_bot_status("bot_1")
        finally:
            await client.aclose()

