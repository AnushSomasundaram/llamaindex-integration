"""Tests for `llama_index_meetstream.tools`."""

from __future__ import annotations

import json

import httpx
import pytest

from llama_index_meetstream.exceptions import MeetStreamAPIError
from llama_index_meetstream.tools import get_meetstream_tools


def _tool(name: str, client):
    return {t.metadata.name: t for t in get_meetstream_tools(client)}[name]


def test_get_meetstream_tools_returns_six_tools(client):
    assert {t.metadata.name for t in get_meetstream_tools(client)} == {
        "dispatch_meetstream_bot",
        "get_meeting",
        "get_meeting_transcript",
        "send_meeting_chat_message",
        "send_meeting_image",
        "leave_meeting",
    }


def test_dispatch_tool_parameters(api_mock, client):
    api_mock.post("/bots/create_bot").mock(
        return_value=httpx.Response(201, json={"bot_id": "bot_1", "transcript_id": "tr_1", "status": "Active"})
    )
    result = _tool("dispatch_meetstream_bot", client).call(meeting_url="https://meet.google.com/abc-defg-hij", bot_name="Standup Bot")

    assert result.raw_output == {"bot_id": "bot_1", "meeting_id": "bot_1", "status": "Active", "transcript_id": "tr_1"}
    sent = json.loads(api_mock.calls.last.request.content)
    assert sent["bot_name"] == "Standup Bot"
    assert sent["recording_config"]["transcript"]["provider"] == {"meetstream": {"language": "auto"}}


def test_dispatch_tool_never_exposes_provider_to_the_model(client):
    schema = _tool("dispatch_meetstream_bot", client).metadata.get_parameters_dict()
    assert set(schema["properties"]) == {"meeting_url", "bot_name"}


def test_get_meeting_tool(api_mock, client):
    api_mock.get("/bots/bot_1/status").mock(return_value=httpx.Response(200, json={"bot_id": "bot_1", "status": "InMeeting"}))
    assert _tool("get_meeting", client).call(meeting_id="bot_1").raw_output["status"] == "InMeeting"


def test_transcript_tool(api_mock, client):
    api_mock.get("/bots/bot_1/get_transcript").mock(return_value=httpx.Response(200, json=[{"transcript": "Hi"}]))
    assert _tool("get_meeting_transcript", client).call(meeting_id="bot_1").raw_output["segments"][0]["text"] == "Hi"


def test_meeting_action_tool_send_chat_message(api_mock, client):
    api_mock.post("/bots/bot_1/send_message").mock(return_value=httpx.Response(200, json={"status": "accepted"}))
    result = _tool("send_meeting_chat_message", client).call(meeting_id="bot_1", message="hello everyone")
    assert result.raw_output["detail"] == "accepted"


def test_meeting_action_tool_leave_meeting(api_mock, client):
    api_mock.get("/bots/bot_1/remove_bot").mock(return_value=httpx.Response(200, json={"status": "stopped"}))
    assert _tool("leave_meeting", client).call(meeting_id="bot_1").raw_output["detail"] == "stopped"


def test_tool_error_propagation(api_mock, client):
    api_mock.get("/bots/missing/get_transcript").mock(return_value=httpx.Response(404, json={"message": "Bot not found"}))
    with pytest.raises(MeetStreamAPIError) as excinfo:
        _tool("get_meeting_transcript", client).call(meeting_id="missing")
    assert excinfo.value.code == "meeting_not_found"


def test_each_tool_has_a_nonempty_description(client):
    for tool in get_meetstream_tools(client):
        assert tool.metadata.description and len(tool.metadata.description) > 20
