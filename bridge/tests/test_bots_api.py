"""Tests for `POST /bots` (bot dispatch)."""

from __future__ import annotations

import httpx


def test_successful_bot_dispatch(client, meetstream_mock):
    meetstream_mock.post("/bots/create_bot").mock(
        return_value=httpx.Response(
            200, json={"bot_id": "bot_123", "transcript_id": None, "meeting_url": "https://meet.google.com/abc-defg-hij", "status": "joining"}
        )
    )

    response = client.post("/bots", json={"meeting_url": "https://meet.google.com/abc-defg-hij", "bot_name": "Standup Bot"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"bot_id": "bot_123", "meeting_id": "bot_123", "status": "joining"}


def test_invalid_bot_dispatch_request_missing_meeting_url(client, meetstream_mock):
    # No `meeting_url` field at all -- FastAPI/Pydantic should reject this
    # before it ever reaches the MeetStream client.
    response = client.post("/bots", json={"bot_name": "Standup Bot"})

    assert response.status_code == 422


def test_bot_dispatch_maps_meetstream_auth_failure(client, meetstream_mock):
    meetstream_mock.post("/bots/create_bot").mock(return_value=httpx.Response(401, json={"detail": "invalid token"}))

    response = client.post("/bots", json={"meeting_url": "https://meet.google.com/abc-defg-hij", "bot_name": "Bot"})

    assert response.status_code == 401
    assert response.json() == {"error": {"code": "authentication_failed", "message": "MeetStream rejected the configured API key"}}


def test_bot_dispatch_maps_invalid_meeting_url(client, meetstream_mock):
    meetstream_mock.post("/bots/create_bot").mock(return_value=httpx.Response(422, json={"detail": "bad url"}))

    response = client.post("/bots", json={"meeting_url": "not-a-real-url", "bot_name": "Bot"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_meeting_url"
