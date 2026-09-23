"""Tests for `llama_index_meetstream.tools`."""

from __future__ import annotations

import httpx
import pytest

from llama_index_meetstream.client import MeetStreamClient
from llama_index_meetstream.exceptions import MeetStreamAPIError
from llama_index_meetstream.tools import get_meetstream_tools

BRIDGE_URL = "http://test-bridge"


def _client() -> MeetStreamClient:
    return MeetStreamClient(api_key="k", base_url=BRIDGE_URL)


def _tool(name: str, client: MeetStreamClient):
    tools = {t.metadata.name: t for t in get_meetstream_tools(client)}
    return tools[name]


def test_get_meetstream_tools_returns_six_tools():
    tools = get_meetstream_tools(_client())
    names = {t.metadata.name for t in tools}
    assert names == {
        "dispatch_meetstream_bot",
        "get_meeting",
        "get_meeting_transcript",
        "send_meeting_chat_message",
        "send_meeting_image",
        "leave_meeting",
    }


def test_dispatch_tool_parameters(bridge_mock):
    bridge_mock.post("/bots").mock(
        return_value=httpx.Response(200, json={"bot_id": "bot_1", "meeting_id": "bot_1", "status": "joining"})
    )
    client = _client()
    tool = _tool("dispatch_meetstream_bot", client)

    result = tool.call(meeting_url="https://meet.google.com/abc-defg-hij", bot_name="Standup Bot")

    assert result.raw_output == {"bot_id": "bot_1", "meeting_id": "bot_1", "status": "joining"}


def test_get_meeting_tool(bridge_mock):
    bridge_mock.get("/meetings/bot_1").mock(
        return_value=httpx.Response(200, json={"meeting_id": "bot_1", "status": "InMeeting", "platform": "zoom"})
    )
    client = _client()
    tool = _tool("get_meeting", client)

    result = tool.call(meeting_id="bot_1")

    assert result.raw_output["status"] == "InMeeting"


def test_transcript_tool(bridge_mock):
    bridge_mock.get("/meetings/bot_1/transcript").mock(
        return_value=httpx.Response(200, json={"meeting_id": "bot_1", "segments": [{"text": "Hi"}]})
    )
    client = _client()
    tool = _tool("get_meeting_transcript", client)

    result = tool.call(meeting_id="bot_1")

    assert result.raw_output["segments"][0]["text"] == "Hi"


def test_meeting_action_tool_send_chat_message(bridge_mock):
    bridge_mock.post("/meetings/bot_1/actions").mock(
        return_value=httpx.Response(200, json={"meeting_id": "bot_1", "action": "send_chat_message", "status": "ok", "detail": "sent"})
    )
    client = _client()
    tool = _tool("send_meeting_chat_message", client)

    result = tool.call(meeting_id="bot_1", message="hello everyone")

    assert result.raw_output["detail"] == "sent"


def test_meeting_action_tool_leave_meeting(bridge_mock):
    bridge_mock.post("/meetings/bot_1/actions").mock(
        return_value=httpx.Response(200, json={"meeting_id": "bot_1", "action": "leave_meeting", "status": "ok", "detail": "removed"})
    )
    client = _client()
    tool = _tool("leave_meeting", client)

    result = tool.call(meeting_id="bot_1")

    assert result.raw_output["detail"] == "removed"


def test_tool_error_propagation(bridge_mock):
    bridge_mock.get("/meetings/missing/transcript").mock(
        return_value=httpx.Response(404, json={"error": {"code": "meeting_not_found", "message": "no such meeting"}})
    )
    client = _client()
    tool = _tool("get_meeting_transcript", client)

    with pytest.raises(MeetStreamAPIError) as excinfo:
        tool.call(meeting_id="missing")
    assert excinfo.value.code == "meeting_not_found"


def test_each_tool_has_a_nonempty_description():
    tools = get_meetstream_tools(_client())
    for tool in tools:
        assert tool.metadata.description and len(tool.metadata.description) > 20
