"""Transcript retrieval and normalization.

Layer: bridge service. See `docs/ARCHITECTURE.md` §3 and §7 before touching
this file: MeetStream's transcript *job* endpoint (`GET
/bots/{id}/transcriptions`) is confirmed by two independent sources, but the
schema of the file at `download_urls.processed_transcript` is not confirmed
byte-for-byte by anything available to this project. This module is the one
place that defensively parses that downloaded content, and the one place a
`TranscriptFormatError` gets raised instead of silently fabricating segments.
"""

from __future__ import annotations

import logging
from typing import Any

from app.clients.meetstream import MeetStreamClient
from app.exceptions import (
    BotNotFoundError,
    MeetingNotFoundError,
    TranscriptFormatError,
    TranscriptNotReadyError,
    TranscriptUnavailableError,
)
from app.models.transcript import Transcript, TranscriptSegment

logger = logging.getLogger(__name__)

# Plausible key names for each field, checked in priority order. Mirrors the
# same defensive-parsing spirit already independently arrived at by
# meeting_digital_twin/src/transcript_utils.py::format_transcript for this
# exact "MeetStream's segment schema isn't pinned down" problem.
_LIST_KEYS = ("segments", "transcript", "results")
_TEXT_KEYS = ("text", "transcript", "punctuated_word")
_SPEAKER_KEYS = ("speaker", "speaker_name", "speaker_label", "speakerName")
_START_KEYS = ("start_time", "start")
_END_KEYS = ("end_time", "end")


async def get_transcript(client: MeetStreamClient, meeting_id: str) -> Transcript:
    """Returns the normalized transcript for `meeting_id` (MeetStream's `bot_id`).

    Raises `TranscriptNotReadyError` if MeetStream is still processing it,
    `TranscriptUnavailableError` if no transcript will ever exist (no job was
    ever created, e.g. the bot was dispatched before this bridge existed or
    without a transcript provider -- or MeetStream's own job `status` came
    back `Failed`), and `MeetingNotFoundError` if the meeting/bot itself
    doesn't exist.
    """
    try:
        raw = await client.get_transcriptions(meeting_id)
    except BotNotFoundError as exc:
        raise MeetingNotFoundError(f"No meeting found for meeting_id={meeting_id}") from exc

    jobs: list[dict[str, Any]] = raw.get("transcriptions") or []
    if not jobs:
        raise TranscriptUnavailableError(
            f"No transcription job exists for meeting_id={meeting_id} "
            "(the bot may have been dispatched without a transcript provider configured)"
        )

    # `created_at` is an ISO timestamp string in every reference source; a
    # plain string sort is sufficient without a datetime parse.
    newest_job = max(jobs, key=lambda job: job.get("created_at") or "")
    status = (newest_job.get("status") or "").lower()

    if status == "processing":
        raise TranscriptNotReadyError(f"Transcript for meeting_id={meeting_id} is still processing")
    if status != "success":
        raise TranscriptUnavailableError(f"Transcript for meeting_id={meeting_id} failed to process (status={status!r})")

    download_urls = newest_job.get("download_urls") or {}
    transcript_url = download_urls.get("processed_transcript") or download_urls.get("raw_transcript")
    if not transcript_url:
        raise TranscriptUnavailableError(
            f"Transcript job for meeting_id={meeting_id} succeeded but returned no download URL"
        )

    content = await client.download_transcript_file(transcript_url)
    segments = _parse_segments(content)
    return Transcript(meeting_id=meeting_id, segments=segments)


def _parse_segments(content: Any) -> list[TranscriptSegment]:
    """Defensively extracts `TranscriptSegment`s from a downloaded transcript
    file's parsed JSON. See this module's docstring for why this is defensive
    rather than a single fixed schema.
    """
    raw_list = content if isinstance(content, list) else None
    if raw_list is None and isinstance(content, dict):
        for key in _LIST_KEYS:
            candidate = content.get(key)
            if isinstance(candidate, list):
                raw_list = candidate
                break

    if raw_list is None:
        raise TranscriptFormatError(
            "Downloaded transcript content did not contain a recognizable list of segments "
            f"(looked for a top-level list or one of {_LIST_KEYS})"
        )

    segments: list[TranscriptSegment] = []
    for index, item in enumerate(raw_list):
        segment = _parse_one_segment(item)
        if segment is None:
            # An individual malformed segment (missing/empty text, or not a
            # dict/str at all) is skipped with a warning rather than failing
            # the entire transcript -- a good transcript with one bad segment
            # is still far more useful to a caller than no transcript at all.
            logger.warning("Skipping malformed transcript segment at index %d", index)
            continue
        segments.append(segment)

    return segments


def _parse_one_segment(item: Any) -> TranscriptSegment | None:
    if isinstance(item, str):
        text = item.strip()
        return TranscriptSegment(text=text) if text else None

    if not isinstance(item, dict):
        return None

    text = _first_present(item, _TEXT_KEYS)
    if not text or not str(text).strip():
        return None

    return TranscriptSegment(
        text=str(text),
        speaker=_first_present(item, _SPEAKER_KEYS),
        start_time=_coerce_float(_first_present(item, _START_KEYS)),
        end_time=_coerce_float(_first_present(item, _END_KEYS)),
    )


def _first_present(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
