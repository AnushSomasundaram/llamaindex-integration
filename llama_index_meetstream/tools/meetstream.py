"""LlamaIndex-native tools for interacting with MeetStream from an agent.

`get_meetstream_tools(client)` is the primary, ergonomic entry point:

    ```python
    from llama_index_meetstream import MeetStreamClient
    from llama_index_meetstream.tools import get_meetstream_tools

    client = MeetStreamClient(api_key="...")
    tools = get_meetstream_tools(client)
    ```

Built on `llama_index.core.tools.FunctionTool` -- the currently recommended
way to expose a plain Python function as an LlamaIndex agent tool (LlamaIndex
also has `BaseToolSpec` for grouping several related tools behind one class,
but a `FunctionTool` per capability plus one aggregating `get_meetstream_tools`
function matches this project's LangChain package 1:1 and needs no extra
abstraction on top). These are plain `FunctionTool` objects -- they work with
any LlamaIndex agent (`llama_index.core.agent.workflow.FunctionAgent`, etc.).
There is no separate "MeetStream agent" class.

Three separate action tools (`send_meeting_chat_message`, `send_meeting_image`,
`leave_meeting`), matching `langchain_meetstream`'s design -- see that
package's `tools/meeting_action.py` for the reasoning: several substantially
different MeetStream actions are clearer as separate, precisely-typed tools
than one vague dict-payload "do an action" tool.
"""

from __future__ import annotations

from llama_index.core.tools import FunctionTool

from llama_index_meetstream.client import MeetStreamClient


def get_dispatch_bot_tool(client: MeetStreamClient) -> FunctionTool:
    """Builds the `dispatch_meetstream_bot` tool bound to `client`."""

    def dispatch_meetstream_bot(meeting_url: str, bot_name: str = "MeetStream Bot") -> dict:
        """Send a MeetStream bot to join a live meeting.

        Use this when a user asks you to record, transcribe, or otherwise
        have a bot join a meeting that is happening now or about to start
        (Google Meet, Zoom, or Microsoft Teams). Returns the new bot's id
        (also usable as meeting_id for get_meeting/get_meeting_transcript/
        meeting-action tools) and its initial join status -- dispatching is
        asynchronous, so the returned status is an early one (e.g. "Active"),
        not yet "in the meeting".

        Args:
            meeting_url (str): The full URL of the meeting to join.
            bot_name (str): The display name the bot should use inside the meeting.
        """
        return client.dispatch_bot(meeting_url=meeting_url, bot_name=bot_name).model_dump()

    return FunctionTool.from_defaults(fn=dispatch_meetstream_bot, name="dispatch_meetstream_bot")


def get_meeting_tool(client: MeetStreamClient) -> FunctionTool:
    """Builds the `get_meeting` tool bound to `client`."""

    def get_meeting(meeting_id: str) -> dict:
        """Look up the current status and metadata of a MeetStream meeting.

        Use this when you need to check whether a bot has actually joined a
        meeting yet, what its current status is, or to confirm a meeting_id
        is valid before calling get_meeting_transcript or a meeting-action tool.
        Several returned fields (title, started_at, ended_at) are commonly
        None -- MeetStream's status endpoint does not expose them.

        Args:
            meeting_id (str): The meeting id returned by dispatch_meetstream_bot.
        """
        return client.get_meeting(meeting_id).model_dump()

    return FunctionTool.from_defaults(fn=get_meeting, name="get_meeting")


def get_transcript_tool(client: MeetStreamClient) -> FunctionTool:
    """Builds the `get_meeting_transcript` tool bound to `client`."""

    def get_meeting_transcript(meeting_id: str) -> dict:
        """Retrieve the transcript for a MeetStream meeting using its meeting ID.

        Use this when you need to inspect, summarize, search, or reason about
        what participants said during a meeting. Returns a dict with
        meeting_id and segments (a list of {text, speaker, start_time,
        end_time} objects, one per speaker turn, in chronological order).
        An empty segments list means a real meeting captured no speech, not
        an error.

        Args:
            meeting_id (str): The meeting id returned by dispatch_meetstream_bot.
        """
        return client.get_transcript(meeting_id).model_dump()

    return FunctionTool.from_defaults(fn=get_meeting_transcript, name="get_meeting_transcript")


def get_send_chat_message_tool(client: MeetStreamClient) -> FunctionTool:
    """Builds the `send_meeting_chat_message` tool bound to `client`."""

    def send_meeting_chat_message(meeting_id: str, message: str) -> dict:
        """Post a text message into a live MeetStream meeting's chat.

        Use this when a user asks you to tell participants something during
        a meeting. Only works while the bot is actively in the meeting.

        Args:
            meeting_id (str): The meeting id returned by dispatch_meetstream_bot.
            message (str): The chat message text to send.
        """
        return client.send_chat_message(meeting_id, message).model_dump()

    return FunctionTool.from_defaults(fn=send_meeting_chat_message, name="send_meeting_chat_message")


def get_send_image_tool(client: MeetStreamClient) -> FunctionTool:
    """Builds the `send_meeting_image` tool bound to `client`."""

    def send_meeting_image(meeting_id: str, image_url: str, display_duration_seconds: float | None = None) -> dict:
        """Display an image as the bot's video feed in a live MeetStream meeting.

        Use this when a user asks you to show a slide, chart, or picture in a
        meeting. image_url must already be a publicly reachable URL --
        MeetStream does not accept inline/base64 image data on this action.

        Args:
            meeting_id (str): The meeting id returned by dispatch_meetstream_bot.
            image_url (str): A publicly reachable URL of the image to display.
            display_duration_seconds (float | None): How long to display the
                image, in seconds. Omit to use MeetStream's default duration.
        """
        return client.send_image(meeting_id, image_url, display_duration_seconds).model_dump()

    return FunctionTool.from_defaults(fn=send_meeting_image, name="send_meeting_image")


def get_leave_meeting_tool(client: MeetStreamClient) -> FunctionTool:
    """Builds the `leave_meeting` tool bound to `client`."""

    def leave_meeting(meeting_id: str) -> dict:
        """Make the MeetStream bot leave a live meeting.

        Use this when a user asks you to remove the bot from a meeting, or a
        meeting has ended and the bot should stop recording. Already-recorded
        data is preserved and remains retrievable via get_meeting_transcript
        after the bot leaves.

        Args:
            meeting_id (str): The meeting id returned by dispatch_meetstream_bot.
        """
        return client.leave_meeting(meeting_id).model_dump()

    return FunctionTool.from_defaults(fn=leave_meeting, name="leave_meeting")


def get_meetstream_tools(client: MeetStreamClient) -> list[FunctionTool]:
    """Returns every MeetStream tool, bound to `client`.

    Covers all four capability areas this integration supports: dispatching a
    bot, retrieving meeting metadata, retrieving a transcript, and performing
    the confirmed-real active-meeting actions (chat message, image, leave).
    """
    return [
        get_dispatch_bot_tool(client),
        get_meeting_tool(client),
        get_transcript_tool(client),
        get_send_chat_message_tool(client),
        get_send_image_tool(client),
        get_leave_meeting_tool(client),
    ]
