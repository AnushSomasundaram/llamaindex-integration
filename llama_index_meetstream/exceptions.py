"""Exceptions raised by `llama_index_meetstream`.

`MeetStreamClient` (see `client.py`) is the one place that turns MeetStream's HTTP
responses into these, so callers can catch one type wherever the call came from.
"""

from __future__ import annotations


class MeetStreamError(Exception):
    """Base class for every exception this package raises."""


class MeetStreamAPIError(MeetStreamError):
    """MeetStream answered with an error, or with a transcript that isn't ready.

    `code` is stable, so callers can branch on it without matching `message`:

    | `code`                     | Meaning                                                        |
    |----------------------------|----------------------------------------------------------------|
    | `authentication_failed`    | MeetStream rejected the API key (401)                          |
    | `forbidden`                | The bot belongs to another account (403)                       |
    | `meeting_not_found`        | No such bot (404)                                              |
    | `invalid_meeting_url`      | `create_bot` rejected the link or settings (400/422)           |
    | `transcript_not_ready`     | Still processing (202); try again later                        |
    | `transcript_unavailable`   | Transcription wasn't enabled, the bot wasn't admitted, or it failed (409/422) |
    | `transcript_format_error`  | The transcript body wasn't in a shape this package understands |
    | `meeting_not_active`       | An in-meeting action, but the bot isn't in a meeting (409)     |
    | `rate_limited`             | Too many requests (429)                                        |
    | `invalid_request`          | Any other 4xx                                                  |
    | `upstream_error`           | MeetStream 5xx, after retries                                  |
    """

    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class MeetStreamConnectionError(MeetStreamError):
    """MeetStream couldn't be reached at all (network error or timeout), as opposed to
    `MeetStreamAPIError`, which means MeetStream answered with an error."""
