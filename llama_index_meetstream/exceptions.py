"""Exceptions raised by `llama_index_meetstream`.

Deliberately identical in shape to `langchain_meetstream.exceptions` -- both
packages wrap the same bridge HTTP contract, and giving each framework
package its own tiny copy of this file (rather than sharing one across
packages) avoids introducing a third, cross-framework published dependency
for what's a few lines of exception classes. See `docs/ARCHITECTURE.md` §8
for the full reasoning.
"""

from __future__ import annotations


class MeetStreamError(Exception):
    """Base class for every exception this package raises."""


class MeetStreamAPIError(MeetStreamError):
    """The bridge server returned an error response.

    `code` is the bridge's own stable error code (e.g. `"transcript_not_ready"`,
    `"meeting_not_found"`) -- see `bridge/app/exceptions.py` for the full set.
    """

    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class MeetStreamConnectionError(MeetStreamError):
    """Could not reach the bridge server at all (network error, timeout, or
    the bridge process isn't running)."""
