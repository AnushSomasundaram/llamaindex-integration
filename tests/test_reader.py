"""Tests for `llama_index_meetstream.readers.MeetStreamReader`."""

from __future__ import annotations

import httpx
import pytest
from llama_index.core.schema import Document

from llama_index_meetstream.client import MeetStreamClient
from llama_index_meetstream.exceptions import MeetStreamAPIError
from llama_index_meetstream.readers import MeetStreamReader

BRIDGE_URL = "http://test-bridge"


def _mock_meeting(bridge_mock, meeting_id: str = "bot_1", title=None, platform="google_meet"):
    bridge_mock.get(f"/meetings/{meeting_id}").mock(
        return_value=httpx.Response(
            200,
            json={"meeting_id": meeting_id, "status": "completed", "platform": platform, "title": title, "meeting_url": None},
        )
    )


def test_reader_returns_one_document_per_segment(bridge_mock):
    bridge_mock.get("/meetings/bot_1/transcript").mock(
        return_value=httpx.Response(
            200,
            json={
                "meeting_id": "bot_1",
                "segments": [
                    {"text": "Engineering should finish this Friday.", "speaker": "Sarah", "start_time": 14.2, "end_time": 18.6},
                    {"text": "Sounds good.", "speaker": "Priya", "start_time": 19.0, "end_time": 20.1},
                ],
            },
        )
    )
    _mock_meeting(bridge_mock)
    client = MeetStreamClient(api_key="k", base_url=BRIDGE_URL)

    docs = MeetStreamReader(meeting_id="bot_1", client=client).load_data()

    assert len(docs) == 2
    assert all(isinstance(d, Document) for d in docs)
    assert docs[0].text == "Engineering should finish this Friday."


def test_reader_metadata_is_correct(bridge_mock):
    bridge_mock.get("/meetings/bot_1/transcript").mock(
        return_value=httpx.Response(
            200, json={"meeting_id": "bot_1", "segments": [{"text": "Hello.", "speaker": "Sarah", "start_time": 1.0, "end_time": 2.0}]}
        )
    )
    _mock_meeting(bridge_mock, title="Engineering Standup")
    client = MeetStreamClient(api_key="k", base_url=BRIDGE_URL)

    [doc] = MeetStreamReader(meeting_id="bot_1", client=client).load_data()

    assert doc.metadata == {
        "source": "meetstream",
        "meeting_id": "bot_1",
        "meeting_title": "Engineering Standup",
        "platform": "google_meet",
        "speaker": "Sarah",
        "start_time": 1.0,
        "end_time": 2.0,
    }


def test_reader_handles_empty_transcript(bridge_mock):
    bridge_mock.get("/meetings/bot_1/transcript").mock(
        return_value=httpx.Response(200, json={"meeting_id": "bot_1", "segments": []})
    )
    _mock_meeting(bridge_mock)
    client = MeetStreamClient(api_key="k", base_url=BRIDGE_URL)

    docs = MeetStreamReader(meeting_id="bot_1", client=client).load_data()

    assert docs == []


def test_reader_handles_missing_speaker_and_timestamps(bridge_mock):
    bridge_mock.get("/meetings/bot_1/transcript").mock(
        return_value=httpx.Response(200, json={"meeting_id": "bot_1", "segments": [{"text": "Anonymous remark."}]})
    )
    _mock_meeting(bridge_mock)
    client = MeetStreamClient(api_key="k", base_url=BRIDGE_URL)

    [doc] = MeetStreamReader(meeting_id="bot_1", client=client).load_data()

    assert doc.metadata["speaker"] is None
    assert doc.metadata["start_time"] is None


def test_reader_invalid_meeting_raises(bridge_mock):
    bridge_mock.get("/meetings/does-not-exist/transcript").mock(
        return_value=httpx.Response(404, json={"error": {"code": "meeting_not_found", "message": "no such meeting"}})
    )
    client = MeetStreamClient(api_key="k", base_url=BRIDGE_URL)

    with pytest.raises(MeetStreamAPIError) as excinfo:
        MeetStreamReader(meeting_id="does-not-exist", client=client).load_data()
    assert excinfo.value.code == "meeting_not_found"


def test_reader_constructs_own_client_from_api_key(bridge_mock):
    bridge_mock.get("/meetings/bot_1/transcript").mock(
        return_value=httpx.Response(200, json={"meeting_id": "bot_1", "segments": []})
    )
    _mock_meeting(bridge_mock)

    docs = MeetStreamReader(meeting_id="bot_1", api_key="k", base_url=BRIDGE_URL).load_data()

    assert docs == []
