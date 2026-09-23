"""Typed models for transcript retrieval.

See `docs/ARCHITECTURE.md` §3 and §7: MeetStream's downloadable transcript
file's exact schema was not confirmed byte-for-byte by any reference source
available to this project, so `TranscriptSegment` intentionally makes every
field but `text` optional, and `app/services/transcript_service.py` is the
one place that defensively parses a few plausible raw shapes into this model.
"""

from __future__ import annotations

from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    """One speaker turn, or one otherwise-atomic chunk of the transcript.

    Deliberately mirrors the shape requested in this project's spec
    (`text`, `speaker`, `start_time`, `end_time`) rather than MeetStream's raw
    downloaded-file field names, which are normalized away by
    `transcript_service.py` before this model is ever constructed.
    """

    text: str
    speaker: str | None = None
    start_time: float | None = None
    end_time: float | None = None


class Transcript(BaseModel):
    """The full normalized transcript for one meeting, returned by
    `GET /meetings/{meeting_id}/transcript`."""

    meeting_id: str
    segments: list[TranscriptSegment]
