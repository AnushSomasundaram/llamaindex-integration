"""Tests for `llama_index_meetstream.client.MeetStreamClient`."""

from __future__ import annotations

import httpx
import pytest

from llama_index_meetstream.client import MeetStreamClient
from llama_index_meetstream.exceptions import MeetStreamAPIError, MeetStreamConnectionError

BRIDGE_URL = "http://test-bridge"


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("MEETSTREAM_API_KEY", raising=False)
    with pytest.raises(ValueError):
        MeetStreamClient(base_url=BRIDGE_URL)


def test_dispatch_bot(bridge_mock):
    bridge_mock.post("/bots").mock(
        return_value=httpx.Response(200, json={"bot_id": "bot_1", "meeting_id": "bot_1", "status": "joining"})
    )
    client = MeetStreamClient(api_key="k", base_url=BRIDGE_URL)

    result = client.dispatch_bot("https://meet.google.com/abc-defg-hij", bot_name="Bot")

    assert result.bot_id == "bot_1"


def test_get_transcript(bridge_mock):
    bridge_mock.get("/meetings/bot_1/transcript").mock(
        return_value=httpx.Response(200, json={"meeting_id": "bot_1", "segments": [{"text": "Hello", "speaker": "Sarah"}]})
    )
    client = MeetStreamClient(api_key="k", base_url=BRIDGE_URL)

    transcript = client.get_transcript("bot_1")

    assert transcript.segments[0].text == "Hello"


def test_bridge_error_response_raises_typed_exception(bridge_mock):
    bridge_mock.get("/meetings/missing/transcript").mock(
        return_value=httpx.Response(404, json={"error": {"code": "meeting_not_found", "message": "No meeting found"}})
    )
    client = MeetStreamClient(api_key="k", base_url=BRIDGE_URL)

    with pytest.raises(MeetStreamAPIError) as excinfo:
        client.get_transcript("missing")

    assert excinfo.value.code == "meeting_not_found"


def test_network_failure_raises_connection_error():
    client = MeetStreamClient(api_key="k", base_url="http://this-host-does-not-exist.invalid", timeout=1.0)
    with pytest.raises(MeetStreamConnectionError):
        client.get_meeting("bot_1")
