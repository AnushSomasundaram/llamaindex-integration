"""Bot dispatch and active-meeting actions.

Layer: bridge service -- sits between the typed HTTP API (`app/api/bots.py`)
and the raw MeetStream client (`app/clients/meetstream.py`). Owns turning
MeetStream's raw JSON into this bridge's typed models and turning MeetStream
HTTP errors into this bridge's exception taxonomy.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from app.clients.meetstream import MeetStreamClient
from app.exceptions import BotNotFoundError, MeetingNotFoundError, UnsupportedActionError
from app.models.bot import (
    BotDispatchRequest,
    BotDispatchResponse,
    LeaveMeetingPayload,
    MeetingActionRequest,
    MeetingActionResponse,
    MeetingActionType,
    SendChatMessagePayload,
    SendImagePayload,
)


async def dispatch_bot(client: MeetStreamClient, request: BotDispatchRequest) -> BotDispatchResponse:
    """Sends a MeetStream bot into a meeting.

    Returns immediately once MeetStream accepts the join request -- the bot's
    status at this point is `"Active"` (confirmed via a real dispatch call --
    see docs/ARCHITECTURE.md §3), not yet `"InMeeting"`; callers that need to
    know when the bot has actually joined should poll
    `GET /meetings/{meeting_id}` (see `meeting_service.get_meeting`), which
    was observed to progress through `"Joining"` -> `"InWaitingRoom"` ->
    `"InMeeting"` in that same real run.
    """
    raw = await client.create_bot(meeting_url=request.meeting_url, bot_name=request.bot_name)
    # `bot_id` doubles as this bridge's `meeting_id` -- see
    # docs/ARCHITECTURE.md §6 for why there is no independent MeetStream
    # meeting identifier to use instead.
    return BotDispatchResponse(bot_id=raw["bot_id"], meeting_id=raw["bot_id"], status=raw["status"])


async def perform_meeting_action(
    client: MeetStreamClient, meeting_id: str, request: MeetingActionRequest
) -> MeetingActionResponse:
    """Performs one of the confirmed-real MeetStream in-meeting actions.

    Each branch below cites which reference implementation
    (docs/ARCHITECTURE.md §3) confirmed that action actually works against the
    live MeetStream API -- this bridge does not expose any MeetStream
    capability it could not find independent, tested confirmation for.
    """
    try:
        if request.action is MeetingActionType.SEND_CHAT_MESSAGE:
            payload = _expect_payload(request, SendChatMessagePayload)
            # Confirmed live-tested in meetstream-gameshow-host/app/meetstream/rest_client.py::send_message.
            raw = await client.send_chat_message(meeting_id, payload.message)
            return MeetingActionResponse(meeting_id=meeting_id, action=request.action, detail=raw.get("message"))

        if request.action is MeetingActionType.SEND_IMAGE:
            payload = _expect_payload(request, SendImagePayload)
            # Confirmed live-tested in meetstream-gameshow-host/app/meetstream/rest_client.py::send_image.
            raw = await client.send_image(meeting_id, payload.image_url, payload.display_duration_seconds)
            return MeetingActionResponse(meeting_id=meeting_id, action=request.action, detail=raw.get("message"))

        if request.action is MeetingActionType.LEAVE_MEETING:
            _expect_payload(request, LeaveMeetingPayload)
            # Confirmed by two independent sources: GET (not DELETE) /bots/{id}/remove_bot.
            raw = await client.remove_bot(meeting_id)
            # `raw` has no `message` field (confirmed via a real, live call --
            # see `MeetStreamClient.remove_bot`'s docstring) -- `status`
            # (e.g. "stopped") is the closest real field to a human-readable
            # outcome for this action.
            return MeetingActionResponse(meeting_id=meeting_id, action=request.action, detail=raw.get("status"))

    except BotNotFoundError as exc:
        # A bot-scoped 404 while performing an action on a specific meeting_id
        # is more precisely "that meeting doesn't exist" from this endpoint's
        # point of view.
        raise MeetingNotFoundError(f"No active meeting found for meeting_id={meeting_id}") from exc

    # Unreachable if MeetingActionType is exhaustively handled above; kept as
    # an explicit guard rather than relying on that silently, since adding a
    # new enum member without a branch here would otherwise fail at the
    # `_expect_payload` call inside a branch that was never taken -- this
    # makes the failure immediate and clear instead.
    raise UnsupportedActionError(f"Unsupported meeting action: {request.action}")


def _expect_payload(request: MeetingActionRequest, expected_type: type[BaseModel]) -> BaseModel:
    """Validates `request.payload` (a loose dict -- see `MeetingActionRequest`'s
    docstring for why) against the specific payload model for this action.
    Turns a Pydantic `ValidationError` (missing/wrong-type field) into this
    bridge's own `UnsupportedActionError` (HTTP 422) rather than letting it
    escape as an unmapped exception.
    """
    try:
        return expected_type.model_validate(request.payload or {})
    except ValidationError as exc:
        raise UnsupportedActionError(
            f"Action {request.action} requires a payload matching {expected_type.__name__}: {exc}"
        ) from exc
