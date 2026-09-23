"""Tests for `GET /meetings/{meeting_id}/transcript`."""

from __future__ import annotations

import httpx


def _transcriptions_response(status: str, processed_transcript_url: str | None = "https://cdn.example.com/t1.json"):
    return {
        "bot_id": "bot_123",
        "transcriptions": [
            {
                "transcript_id": "t1",
                "provider": "deepgram",
                "status": status,
                "created_at": "2026-01-01T00:00:00Z",
                "download_urls": {"processed_transcript": processed_transcript_url} if processed_transcript_url else {},
            }
        ],
    }


def test_successful_transcript_retrieval(client, meetstream_mock):
    meetstream_mock.get("/bots/bot_123/transcriptions").mock(
        return_value=httpx.Response(200, json=_transcriptions_response("Success"))
    )
    meetstream_mock.get("https://cdn.example.com/t1.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "segments": [
                    {"text": "Engineering should finish this Friday.", "speaker": "Sarah", "start_time": 14.2, "end_time": 18.6},
                    {"text": "Sounds good.", "speaker": "Priya", "start": 19.0, "end": 20.1},
                ]
            },
        )
    )

    response = client.get("/meetings/bot_123/transcript")

    assert response.status_code == 200
    body = response.json()
    assert body["meeting_id"] == "bot_123"
    assert body["segments"] == [
        {"text": "Engineering should finish this Friday.", "speaker": "Sarah", "start_time": 14.2, "end_time": 18.6},
        {"text": "Sounds good.", "speaker": "Priya", "start_time": 19.0, "end_time": 20.1},
    ]


def test_transcript_not_ready(client, meetstream_mock):
    meetstream_mock.get("/bots/bot_123/transcriptions").mock(
        return_value=httpx.Response(200, json=_transcriptions_response("Processing", processed_transcript_url=None))
    )

    response = client.get("/meetings/bot_123/transcript")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "transcript_not_ready"


def test_transcript_unavailable_when_no_job_exists(client, meetstream_mock):
    meetstream_mock.get("/bots/bot_123/transcriptions").mock(
        return_value=httpx.Response(200, json={"bot_id": "bot_123", "transcriptions": []})
    )

    response = client.get("/meetings/bot_123/transcript")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "transcript_unavailable"


def test_transcript_unavailable_when_job_failed(client, meetstream_mock):
    meetstream_mock.get("/bots/bot_123/transcriptions").mock(
        return_value=httpx.Response(200, json=_transcriptions_response("Failed", processed_transcript_url=None))
    )

    response = client.get("/meetings/bot_123/transcript")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "transcript_unavailable"


def test_transcript_upstream_auth_failure(client, meetstream_mock):
    meetstream_mock.get("/bots/bot_123/transcriptions").mock(return_value=httpx.Response(401, json={}))

    response = client.get("/meetings/bot_123/transcript")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


def test_transcript_upstream_network_failure(client, meetstream_mock):
    meetstream_mock.get("/bots/bot_123/transcriptions").mock(side_effect=httpx.ConnectError("connection refused"))

    response = client.get("/meetings/bot_123/transcript")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"


def test_transcript_malformed_segments_are_skipped_not_fatal(client, meetstream_mock):
    meetstream_mock.get("/bots/bot_123/transcriptions").mock(
        return_value=httpx.Response(200, json=_transcriptions_response("Success"))
    )
    meetstream_mock.get("https://cdn.example.com/t1.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "segments": [
                    {"text": "Real segment.", "speaker": "Sarah"},
                    {"speaker": "Unknown"},  # missing text -- malformed, should be skipped
                    "",  # empty string -- malformed, should be skipped
                    42,  # wrong type entirely -- malformed, should be skipped
                ]
            },
        )
    )

    response = client.get("/meetings/bot_123/transcript")

    assert response.status_code == 200
    segments = response.json()["segments"]
    assert len(segments) == 1
    assert segments[0]["text"] == "Real segment."


def test_transcript_missing_speaker_and_timestamps(client, meetstream_mock):
    meetstream_mock.get("/bots/bot_123/transcriptions").mock(
        return_value=httpx.Response(200, json=_transcriptions_response("Success"))
    )
    meetstream_mock.get("https://cdn.example.com/t1.json").mock(
        return_value=httpx.Response(200, json={"segments": [{"text": "Anonymous remark."}]})
    )

    response = client.get("/meetings/bot_123/transcript")

    assert response.status_code == 200
    segment = response.json()["segments"][0]
    assert segment == {"text": "Anonymous remark.", "speaker": None, "start_time": None, "end_time": None}
