"""Typed models for the bot-dispatch operation.

These mirror the bridge's own normalized request/response shape (see
`docs/ARCHITECTURE.md` §6 for why `meeting_id` here *is* MeetStream's
`bot_id`), not MeetStream's raw `CreateBotRequest`/`CreateBotResponse` JSON —
that raw shape only ever exists inside
`app/clients/meetstream.py::MeetStreamClient.create_bot`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class BotDispatchRequest(BaseModel):
    """What a caller sends to `POST /bots` to send a bot into a meeting."""

    meeting_url: str = Field(..., description="The meeting URL to join (Google Meet, Zoom, or Teams).")
    bot_name: str = Field(default="MeetStream Bot", description="Display name the bot uses in the meeting.")


class BotDispatchResponse(BaseModel):
    """What the bridge returns after dispatching a bot.

    `status` is passed through verbatim from MeetStream's `CreateBotResponse.status`
    (e.g. `"Active"`, confirmed via a real dispatch call -- see
    docs/ARCHITECTURE.md §3) rather than remapped to a bridge-invented enum, since
    MeetStream's set of possible dispatch-time statuses isn't fully enumerated
    in any of the reference sources this project could confirm against (see
    docs/ARCHITECTURE.md §3).
    """

    bot_id: str
    meeting_id: str
    status: str


class MeetingActionType(str, Enum):
    """The MeetStream capabilities this bridge exposes as an "active meeting
    action", scoped to ones confirmed real and working against MeetStream's
    actual API by at least one of the reference implementations in
    docs/ARCHITECTURE.md §3 -- see `app/services/bot_service.py` for the
    per-action docstring citing exactly which source confirmed each one.

    Deliberately excludes MeetStream capabilities that exist but are not
    "actions on an active meeting" in the sense this endpoint covers, e.g.
    `get_chats` (a read, exposed instead by transcript/meeting retrieval-style
    semantics) and MIA agent-config management (a separate configuration
    resource, not a meeting-time action).
    """

    SEND_CHAT_MESSAGE = "send_chat_message"
    SEND_IMAGE = "send_image"
    LEAVE_MEETING = "leave_meeting"


class SendChatMessagePayload(BaseModel):
    message: str = Field(..., description="The text to post into the meeting's chat.")


class SendImagePayload(BaseModel):
    image_url: str = Field(..., description="A publicly reachable URL of the image to display as the bot's video feed.")
    display_duration_seconds: float | None = Field(
        default=None, description="How long to display the image, in seconds. Omit to use MeetStream's default."
    )


class LeaveMeetingPayload(BaseModel):
    """No fields: leaving a meeting only needs the bot/meeting id already in the URL path."""


class MeetingActionRequest(BaseModel):
    """`payload`'s shape depends on `action` (a `send_chat_message` needs a
    `message`, a `leave_meeting` needs nothing), but Pydantic has no built-in
    way to discriminate a `Union` on a *sibling* field the way it can on a
    tag living inside the union member itself -- an untyped `payload: dict`
    here would happily accept `{}` for every action, including ones that
    require a field. So `payload` stays a loose `dict` at this layer, and
    `app/services/bot_service.py::_expect_payload` is the one place that
    validates it against the specific `SendChatMessagePayload` /
    `SendImagePayload` / `LeaveMeetingPayload` model that matches `action`,
    turning a mismatch into a 422 rather than silently accepting it.
    """

    action: MeetingActionType
    payload: dict[str, Any] | None = None


class MeetingActionResponse(BaseModel):
    meeting_id: str
    action: MeetingActionType
    status: Literal["ok"] = "ok"
    detail: str | None = None
    """MeetStream's own human-readable response message, if it returned one
    (e.g. remove_bot's `{"message": ...}`)."""
