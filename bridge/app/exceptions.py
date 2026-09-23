"""The bridge's error taxonomy.

Every error the bridge can raise is one of these types. `app/main.py` registers
a single exception handler per type (see `register_exception_handlers`) that
maps it to a stable JSON body and HTTP status. Nothing else in this codebase
should raise a bare `Exception`, `httpx.HTTPStatusError`, or `ValueError` past
its own module boundary — catch those close to the MeetStream call site and
re-raise as one of these, so callers of the bridge only ever see this one,
documented set of failure modes instead of leaking MeetStream's own error
shapes or a raw stack trace.
"""

from __future__ import annotations


class MeetStreamBridgeError(Exception):
    """Base class for every error this bridge intentionally raises.

    `code` is a short, stable, machine-readable string returned in the JSON
    error body (`{"error": {"code": ..., "message": ...}}`) so that API
    consumers (including the LangChain/LlamaIndex packages) can branch on
    failure type without parsing prose.
    """

    code: str = "meetstream_error"
    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MeetStreamAuthError(MeetStreamBridgeError):
    """The configured MeetStream API key was rejected (HTTP 401/403 upstream)."""

    code = "authentication_failed"
    status_code = 401


class MeetingNotFoundError(MeetStreamBridgeError):
    """No MeetStream bot/meeting exists for the given meeting_id (HTTP 404 upstream)."""

    code = "meeting_not_found"
    status_code = 404


class BotNotFoundError(MeetStreamBridgeError):
    """No MeetStream bot exists for the given bot_id (HTTP 404 upstream on a bot-scoped call)."""

    code = "bot_not_found"
    status_code = 404


class InvalidMeetingURLError(MeetStreamBridgeError):
    """The supplied meeting URL was rejected by MeetStream as malformed or unreachable."""

    code = "invalid_meeting_url"
    status_code = 422


class UnsupportedPlatformError(MeetStreamBridgeError):
    """The meeting URL's platform is not one MeetStream (or this bridge) supports."""

    code = "unsupported_platform"
    status_code = 422


class TranscriptNotReadyError(MeetStreamBridgeError):
    """A transcription job exists but has not finished processing yet.

    Distinct from `TranscriptUnavailableError`: this means "ask again later,"
    not "this will never succeed."
    """

    code = "transcript_not_ready"
    status_code = 409


class TranscriptUnavailableError(MeetStreamBridgeError):
    """No transcript will ever be produced for this meeting.

    Covers both "no transcription job was ever created" (the bot was
    dispatched without a transcript provider configured) and "the job failed"
    (MeetStream's own `status` came back `Failed`).
    """

    code = "transcript_unavailable"
    status_code = 404


class UnsupportedActionError(MeetStreamBridgeError):
    """The requested meeting action is not one MeetStream actually supports.

    Raised by the bridge itself (not MeetStream) when a caller asks for an
    action outside the confirmed set in `app/services/bot_service.py` — see
    that module's docstring for exactly which actions are real.
    """

    code = "unsupported_action"
    status_code = 422


class UpstreamError(MeetStreamBridgeError):
    """MeetStream returned an unexpected 4xx/5xx this bridge doesn't have a more
    specific mapping for. The original MeetStream status code is preserved in
    `upstream_status_code` for logging, but never echoed into the response body
    the way `httpx.HTTPStatusError`'s message would (that could leak upstream
    response content, potentially including data not meant for the caller)."""

    code = "upstream_error"
    status_code = 502

    def __init__(self, message: str, upstream_status_code: int | None = None) -> None:
        super().__init__(message)
        self.upstream_status_code = upstream_status_code


class UpstreamTimeoutError(MeetStreamBridgeError):
    """MeetStream did not respond within `meetstream_request_timeout_seconds`."""

    code = "upstream_timeout"
    status_code = 504


class TranscriptFormatError(MeetStreamBridgeError):
    """A transcript file was downloaded from MeetStream but its content did not
    match any of the shapes `app/services/transcript_service.py` knows how to
    parse. Raised instead of guessing at fields or returning an empty
    transcript, since MeetStream's downloaded-file schema is not byte-for-byte
    confirmed by any source available to this project -- see
    docs/ARCHITECTURE.md §3.
    """

    code = "transcript_format_error"
    status_code = 502
