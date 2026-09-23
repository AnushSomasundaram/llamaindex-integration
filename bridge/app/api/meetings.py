"""`GET /meetings/{meeting_id}` and `POST /meetings/{meeting_id}/actions`.

Layer: HTTP API. See `app/services/meeting_service.py` and
`app/services/bot_service.py` for the actual logic; this module is routing
and request/response typing only.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.bot import MeetingActionRequest, MeetingActionResponse
from app.models.meeting import MeetingMetadata
from app.services import bot_service, meeting_service

router = APIRouter(tags=["meetings"])


@router.get("/meetings/{meeting_id}", response_model=MeetingMetadata)
async def get_meeting(request: Request, meeting_id: str) -> MeetingMetadata:
    return await meeting_service.get_meeting(request.app.state.meetstream_client, meeting_id)


@router.post("/meetings/{meeting_id}/actions", response_model=MeetingActionResponse)
async def perform_meeting_action(
    request: Request, meeting_id: str, body: MeetingActionRequest
) -> MeetingActionResponse:
    return await bot_service.perform_meeting_action(request.app.state.meetstream_client, meeting_id, body)
