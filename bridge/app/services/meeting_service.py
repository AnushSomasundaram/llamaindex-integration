"""Meeting metadata retrieval and normalization.

Layer: bridge service. See `docs/ARCHITECTURE.md` §6 before touching this
file -- every field `MeetingMetadata` can return (or can't) is documented
there with the reason, and this module is where that contract is implemented.
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.clients.meetstream import MeetStreamClient
from app.exceptions import BotNotFoundError, MeetingNotFoundError
from app.models.meeting import MeetingMetadata

# Hostname substrings -> normalized platform name. Order doesn't matter since
# these are checked with `in`, not exact match, against the full netloc
# (covers subdomains like `xyz.zoom.us`). This is a *guess* derived from the
# URL, not a field MeetStream's API returns -- see docs/ARCHITECTURE.md §6.
_PLATFORM_HOSTS: dict[str, str] = {
    "meet.google.com": "google_meet",
    "zoom.us": "zoom",
    "teams.microsoft.com": "teams",
    "teams.live.com": "teams",
}


def infer_platform(meeting_url: str | None) -> str | None:
    """Best-effort platform guess from a meeting URL's hostname.

    Returns `None` (never a guessed value) when `meeting_url` is `None` or its
    host doesn't match a known platform -- this bridge would rather report
    "unknown" than silently mislabel a meeting.
    """
    if not meeting_url:
        return None
    host = urlparse(meeting_url).netloc.lower()
    for known_host, platform in _PLATFORM_HOSTS.items():
        if known_host in host:
            return platform
    return None


async def get_meeting(
    client: MeetStreamClient, meeting_id: str, *, known_meeting_url: str | None = None
) -> MeetingMetadata:
    """Normalized meeting metadata for `meeting_id` (MeetStream's `bot_id`).

    `known_meeting_url` lets a caller that just dispatched this same bot (and
    therefore has MeetStream's `meeting_url` from that response) pass it
    through so `platform` can be inferred -- see docs/ARCHITECTURE.md §6 for
    why this bridge cannot recover that URL on its own from the status
    endpoint alone. Omit it (the normal case for a `GET /meetings/{id}` call
    made later, in a separate request) and `meeting_url`/`platform` come back
    `None`.
    """
    try:
        raw = await client.get_bot_status(meeting_id)
    except BotNotFoundError as exc:
        raise MeetingNotFoundError(f"No meeting found for meeting_id={meeting_id}") from exc

    return MeetingMetadata(
        meeting_id=meeting_id,
        status=raw["status"],
        platform=infer_platform(known_meeting_url),
        meeting_url=known_meeting_url,
        custom_attributes=raw.get("custom_attributes") or None,
    )
