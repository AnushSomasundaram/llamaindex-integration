"""Tests for `GET /meetings/{meeting_id}` and `POST /meetings/{meeting_id}/actions`."""

from __future__ import annotations

import httpx


def test_get_meeting_returns_normalized_metadata(client, meetstream_mock):
    meetstream_mock.get("/bots/bot_123/status").mock(
        return_value=httpx.Response(200, json={"bot_id": "bot_123", "status": "InMeeting", "custom_attributes": {"team": "eng"}})
    )

    response = client.get("/meetings/bot_123")

    assert response.status_code == 200
    body = response.json()
    assert body["meeting_id"] == "bot_123"
    assert body["status"] == "InMeeting"
    assert body["custom_attributes"] == {"team": "eng"}
    # Not knowable from this endpoint alone -- see docs/ARCHITECTURE.md §6.
    assert body["title"] is None
    assert body["started_at"] is None
    assert body["meeting_url"] is None


def test_get_meeting_not_found(client, meetstream_mock):
    meetstream_mock.get("/bots/does-not-exist/status").mock(return_value=httpx.Response(404, json={"detail": "not found"}))

    response = client.get("/meetings/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "meeting_not_found"


def test_meeting_action_send_chat_message(client, meetstream_mock):
    meetstream_mock.post("/bots/bot_123/send_message").mock(return_value=httpx.Response(200, json={"message": "sent"}))

    response = client.post(
        "/meetings/bot_123/actions",
        json={"action": "send_chat_message", "payload": {"message": "Standup starting now"}},
    )

    assert response.status_code == 200
    assert response.json() == {"meeting_id": "bot_123", "action": "send_chat_message", "status": "ok", "detail": "sent"}


def test_meeting_action_leave_meeting(client, meetstream_mock):
    # Real shape confirmed via a live call against MeetStream's actual API --
    # no `message` field (see MeetStreamClient.remove_bot's docstring).
    meetstream_mock.get("/bots/bot_123/remove_bot").mock(
        return_value=httpx.Response(200, json={"bot_id": "bot_123", "status": "stopped", "bot_status": "MediaProcessing"})
    )

    response = client.post("/meetings/bot_123/actions", json={"action": "leave_meeting"})

    assert response.status_code == 200
    assert response.json()["detail"] == "stopped"


def test_meeting_action_requires_matching_payload(client, meetstream_mock):
    # send_chat_message requires a `message` field in its payload.
    response = client.post("/meetings/bot_123/actions", json={"action": "send_chat_message", "payload": {}})

    assert response.status_code == 422


def test_meeting_action_on_missing_meeting_maps_to_meeting_not_found(client, meetstream_mock):
    meetstream_mock.post("/bots/bot_missing/send_message").mock(return_value=httpx.Response(404, json={}))

    response = client.post(
        "/meetings/bot_missing/actions",
        json={"action": "send_chat_message", "payload": {"message": "hi"}},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "meeting_not_found"
