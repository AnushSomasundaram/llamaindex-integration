"""The only module in this repository that talks to the real MeetStream REST API.

Every endpoint path, header, and raw JSON field name below is confirmed against
independently-written, live-tested MeetStream clients found elsewhere on this
machine (see `docs/ARCHITECTURE.md` §3) -- specifically the agreement between
`meetstream-gameshow-host/app/meetstream/rest_client.py` (Python/httpx) and
`meetstream-minutes/lib/meetstream/{client,types}.ts` (TypeScript). No endpoint
here was invented; where those two sources disagreed with a third, weaker
source, the two-source agreement won (see the same section for the specifics).

This module returns MeetStream's raw response `dict`s (via `.json()`) rather
than typed models -- turning those into this bridge's own typed,
normalized models is `app/services/*`'s job, not this module's. Keeping that
boundary means a MeetStream field rename only ever requires touching the one
service function that reads that field, not this client.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.exceptions import (
    BotNotFoundError,
    InvalidMeetingURLError,
    MeetStreamAuthError,
    UpstreamError,
    UpstreamTimeoutError,
)

logger = logging.getLogger(__name__)

# MeetStream's own server has been observed, live, to return a transient 503
# that succeeds on an immediate retry (see rest_client.py's docstring in
# meetstream-gameshow-host, which this policy is copied from verbatim).
# Retries are only applied to requests that are safe to repeat -- GETs, and
# the specific POSTs below that are naturally idempotent-ish (re-sending the
# same chat message or re-displaying the same image on transient failure is
# an acceptable outcome; MeetStream duplicate-bot-joining is not, so
# `create_bot` is deliberately NOT retried here -- see `create_bot`'s own
# docstring).
_MAX_RETRIES = 3
_RETRY_BASE_DELAY_SECONDS = 1.0


class MeetStreamClient:
    """Thin async wrapper over the MeetStream REST API.

    Layer: the bottom of the bridge -- `app/services/*` is the only code that
    should import this class. Holds one connection-pooled `httpx.AsyncClient`
    per instance (not per request), matching the pattern already confirmed to
    work in `meetstream-gameshow-host/app/meetstream/rest_client.py`.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.meetstream.ai/api/v1",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # Confirmed via a real MeetStream API call (not just docs) by
        # meetstream-gameshow-host: the header value is the literal word
        # "Token", not "Bearer" or a raw API-key header.
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Token {api_key}"},
            timeout=timeout_seconds,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        retry: bool = False,
    ) -> dict[str, Any] | None:
        """Shared request path for every MeetStream call.

        Raises this bridge's own exception types directly (rather than
        `httpx.HTTPStatusError`) so every call site in `app/services/*` deals
        with one consistent error taxonomy regardless of which MeetStream
        endpoint it called -- see `app/exceptions.py`.
        """
        attempts = _MAX_RETRIES if retry else 1
        for attempt in range(attempts):
            try:
                response = await self._client.request(method, path, json=json)
            except httpx.TimeoutException as exc:
                raise UpstreamTimeoutError(f"MeetStream did not respond to {method} {path} in time") from exc
            except httpx.HTTPError as exc:
                raise UpstreamError(f"Network error calling MeetStream {method} {path}: {exc}") from exc

            if response.status_code < 400:
                return response.json() if response.content else None

            if response.status_code >= 500 and retry and attempt < attempts - 1:
                delay = _RETRY_BASE_DELAY_SECONDS * (2**attempt)
                logger.warning(
                    "MeetStream %s %s returned %d -- retrying in %.1fs (attempt %d/%d)",
                    method,
                    path,
                    response.status_code,
                    delay,
                    attempt + 1,
                    attempts,
                )
                await asyncio.sleep(delay)
                continue

            # Deliberately not logging response.text here: it may contain
            # account-identifying or otherwise sensitive upstream content, and
            # nothing downstream needs the raw body -- only the status code
            # and our own mapped exception type.
            raise _map_error_response(method, path, response.status_code)

        # Only reached if every retry attempt hit a 5xx.
        raise UpstreamError(f"MeetStream {method} {path} failed after {attempts} attempts (persistent 5xx)")

    async def create_bot(self, meeting_url: str, bot_name: str) -> dict[str, Any]:
        """`POST /bots/create_bot`. Returns MeetStream's raw
        `{bot_id, transcript_id, meeting_url, status}`.

        Not retried on failure -- see this module's docstring: blindly
        repeating a bot-creation request risks a second, real bot joining the
        same meeting if the first request actually succeeded and only the
        response was lost.

        Sets `recording_config.transcript.provider.deepgram` unconditionally.
        This is an explicit, documented assumption (see docs/ARCHITECTURE.md
        §3): MeetStream requires a transcript provider to be selected at
        dispatch time for a transcription job to be created at all, confirmed
        by `meeting_digital_twin/src/meetstream_client.py`'s working
        `create_bot` call. Without this, `get_transcriptions` would later
        return an empty job list with no way to distinguish "not ready yet"
        from "never configured."
        """
        payload = {
            "meeting_link": meeting_url,
            "bot_name": bot_name,
            "recording_config": {"transcript": {"provider": {"deepgram": {"model": "nova-3", "language": "en"}}}},
        }
        result = await self._request("POST", "/bots/create_bot", json=payload, retry=False)
        assert result is not None
        return result

    async def get_bot_status(self, bot_id: str) -> dict[str, Any]:
        """`GET /bots/{bot_id}/status`. Returns MeetStream's raw
        `{bot_id, status, custom_attributes}`."""
        result = await self._request("GET", f"/bots/{bot_id}/status", retry=True)
        assert result is not None
        return result

    async def get_transcriptions(self, bot_id: str) -> dict[str, Any]:
        """`GET /bots/{bot_id}/transcriptions`. Returns MeetStream's raw
        `{bot_id, transcriptions: [{transcript_id, provider, status,
        created_at, download_urls: {raw_transcript, processed_transcript}}]}`.

        Note this is a list of transcription *jobs*, not transcript content --
        `app/services/transcript_service.py` is responsible for picking a job
        and downloading its `processed_transcript` URL. See
        docs/ARCHITECTURE.md §3 and §7.
        """
        result = await self._request("GET", f"/bots/{bot_id}/transcriptions", retry=True)
        assert result is not None
        return result

    async def download_transcript_file(self, url: str) -> Any:
        """Fetches the content at a `download_urls.processed_transcript` link.

        This is a plain GET to a (likely pre-signed, likely non-MeetStream-
        domain) URL MeetStream itself returned -- not an authenticated
        MeetStream API call, so it deliberately does NOT go through
        `self._client` (which would attach this bridge's `Authorization:
        Token` header to a third-party storage URL that doesn't expect it,
        and in the case of a signed URL, doesn't need it).
        """
        async with httpx.AsyncClient(timeout=self._client.timeout) as download_client:
            try:
                response = await download_client.get(url)
            except httpx.TimeoutException as exc:
                raise UpstreamTimeoutError("Timed out downloading transcript file from MeetStream") from exc
            except httpx.HTTPError as exc:
                raise UpstreamError(f"Network error downloading transcript file: {exc}") from exc
            if response.status_code >= 400:
                raise UpstreamError(
                    f"Failed to download transcript file (HTTP {response.status_code})",
                    upstream_status_code=response.status_code,
                )
            return response.json()

    async def send_chat_message(self, bot_id: str, message: str) -> dict[str, Any]:
        """`POST /bots/{bot_id}/send_message`."""
        result = await self._request("POST", f"/bots/{bot_id}/send_message", json={"message": message}, retry=True)
        return result or {}

    async def send_image(self, bot_id: str, image_url: str, display_duration: float | None) -> dict[str, Any]:
        """`POST /bots/{bot_id}/send_image`. `image_url` must be publicly
        reachable -- MeetStream rejects inline base64 image data on this
        endpoint (confirmed by meetstream-gameshow-host)."""
        payload: dict[str, Any] = {"img_url": image_url}
        if display_duration is not None:
            payload["display_duration"] = display_duration
        result = await self._request("POST", f"/bots/{bot_id}/send_image", json=payload, retry=True)
        return result or {}

    async def remove_bot(self, bot_id: str) -> dict[str, Any]:
        """`GET /bots/{bot_id}/remove_bot` -- yes, GET, not DELETE; confirmed
        by two independent sources (see docs/ARCHITECTURE.md §3). Makes the
        bot leave the meeting; recorded data is preserved.

        Returns MeetStream's raw `{bot_id, status, bot_status,
        control_request_id, requested_at, acknowledged_at, completed_at}` --
        confirmed via a real, live call against a real meeting (see
        docs/ARCHITECTURE.md §3). Notably there is NO `message` field, unlike
        the `{message: string}` shape the reference TypeScript client assumed
        -- that assumption was wrong and has been corrected here and in
        `app/services/bot_service.py`.
        """
        result = await self._request("GET", f"/bots/{bot_id}/remove_bot", retry=True)
        return result or {}


def _map_error_response(method: str, path: str, status_code: int) -> Exception:
    """Maps a MeetStream HTTP status code to this bridge's exception
    taxonomy. Deliberately status-code-driven rather than parsing MeetStream's
    error response body: the body's shape isn't confirmed/stable across
    endpoints in any reference source, but HTTP status codes are a contract
    every REST API is expected to honor.
    """
    if status_code in (401, 403):
        return MeetStreamAuthError("MeetStream rejected the configured API key")
    if status_code == 404:
        # Bot-scoped paths (`/bots/{id}/...`) vs. the create endpoint both
        # 404 the same way at the HTTP layer; callers that know which
        # resource they were asking about (bot vs. meeting) raise the more
        # specific of BotNotFoundError/MeetingNotFoundError themselves after
        # catching this -- see app/services/*.
        return BotNotFoundError(f"MeetStream returned 404 for {method} {path}")
    if status_code == 422:
        return InvalidMeetingURLError(f"MeetStream rejected the request as invalid ({method} {path})")
    return UpstreamError(f"MeetStream {method} {path} failed with status {status_code}", upstream_status_code=status_code)
