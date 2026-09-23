"""`GET /meetings/{meeting_id}/transcript`.

Layer: HTTP API. See `app/services/transcript_service.py` for the actual
retrieval/normalization logic.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.transcript import Transcript
from app.services import transcript_service

router = APIRouter(tags=["transcripts"])


@router.get("/meetings/{meeting_id}/transcript", response_model=Transcript)
async def get_transcript(request: Request, meeting_id: str) -> Transcript:
    return await transcript_service.get_transcript(request.app.state.meetstream_client, meeting_id)
