"""Typed models for meeting metadata retrieval.

See `docs/ARCHITECTURE.md` §6 ("Meeting metadata: what's real vs. derived vs.
unavailable") before changing any field here. Every `None`-able field here is
`None`-able for a documented reason, not because validation was skipped.
"""

from __future__ import annotations

from pydantic import BaseModel


class MeetingMetadata(BaseModel):
    """Normalized view of a meeting/bot, returned by `GET /meetings/{meeting_id}`."""

    meeting_id: str
    status: str
    """MeetStream's own bot status string (e.g. "InMeeting"), passed through as-is."""

    platform: str | None = None
    """Inferred from the meeting URL's hostname when the URL is known; see
    `app/services/meeting_service.py::infer_platform`. `None` if the URL is
    unknown or unrecognized -- never guessed."""

    meeting_url: str | None = None
    """Only known within the same process that dispatched the bot (the bridge
    holds no database -- see docs/ARCHITECTURE.md §9). `None` on a fresh
    `GET /meetings/{meeting_id}` call, since MeetStream's own status endpoint
    does not return it."""

    title: str | None = None
    """TODO: MeetStream's API does not expose a meeting title anywhere this
    project could confirm. Always None until MeetStream's API provides one."""

    started_at: str | None = None
    ended_at: str | None = None
    """TODO: only available via MeetStream's webhook lifecycle events, which
    this stateless bridge does not ingest in v0.1 -- see
    docs/ARCHITECTURE.md §10. Always None from this synchronous endpoint."""

    custom_attributes: dict[str, object] | None = None
    """Passed through from MeetStream's bot status response, if present."""
