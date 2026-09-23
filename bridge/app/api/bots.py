"""`POST /bots` -- dispatches a MeetStream bot into a meeting.

Layer: HTTP API. Translates between FastAPI's request/response cycle and
`app/services/bot_service.py`; contains no MeetStream-specific logic itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.bot import BotDispatchRequest, BotDispatchResponse
from app.services import bot_service

router = APIRouter(tags=["bots"])


@router.post("/bots", response_model=BotDispatchResponse)
async def create_bot(request: Request, body: BotDispatchRequest) -> BotDispatchResponse:
    return await bot_service.dispatch_bot(request.app.state.meetstream_client, body)
