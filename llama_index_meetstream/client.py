"""`MeetStreamClient`: the HTTP client this package uses to call MeetStream's REST API.

The reader (`readers/meetstream.py`) and every tool under `tools/` share
this client, so there is one place that knows MeetStream's paths, auth header,
response shapes and error codes. It calls `https://api.meetstream.ai/api/v1`
directly, with your MeetStream API key; no separate server is involved.

Endpoints used (see https://docs.meetstream.ai/api-reference):

| Method                     | MeetStream call                       |
|----------------------------|---------------------------------------|
| `dispatch_bot`             | `POST /bots/create_bot`               |
| `get_meeting`              | `GET /bots/{bot_id}/status`           |
| `get_transcript`           | `GET /bots/{bot_id}/get_transcript`   |
| `send_chat_message`        | `POST /bots/{bot_id}/send_message`    |
| `send_image`               | `POST /bots/{bot_id}/send_image`      |
| `leave_meeting`            | `GET /bots/{bot_id}/remove_bot`       |
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Literal
from urllib.parse import quote, urlparse

import httpx
from pydantic import BaseModel

from llama_index_meetstream.exceptions import MeetStreamAPIError, MeetStreamConnectionError

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.meetstream.ai/api/v1"

DEFAULT_TRANSCRIPTION_PROVIDER = "meetstream"
"""MeetStream's own post-call transcription. Used unless you choose another provider."""

TRANSCRIPTION_PROVIDERS = (
    "meetstream",
    "deepgram",
    "assemblyai",
    "jigsawstack",
    "sarvam",
    "smallest",
    "meeting_captions",
)
"""Post-call providers MeetStream documents for `recording_config.transcript.provider`.

Not enforced: any provider name MeetStream accepts can be passed. Some need an
integration key saved in the MeetStream dashboard first (for example `smallest`).
"""

_DEFAULT_PROVIDER_OPTIONS: dict[str, dict[str, Any]] = {"meetstream": {"language": "auto"}}

# Transient server errors MeetStream documents as safe to retry with backoff.
_RETRY_STATUSES = frozenset({500, 502, 503, 504})
# For chat messages and images, only 503 ("command channel not connected yet") means the
# command wasn't accepted; after a 500 it may already have gone through, so it isn't repeated.
_COMMAND_RETRY_STATUSES = frozenset({503})
_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_SECONDS = 1.0

_UNSET: Any = object()

_PLATFORM_HOSTS = {
    "meet.google.com": "google_meet",
    "zoom.us": "zoom",
    "teams.microsoft.com": "teams",
    "teams.live.com": "teams",
}


class MeetingMetadata(BaseModel):
    """A meeting's current state. `meeting_id` is MeetStream's `bot_id`.

    MeetStream's status endpoint returns only `status` and `custom_attributes`.
    `meeting_url` and `platform` are filled in when this client dispatched the bot
    itself; `title`, `started_at` and `ended_at` are not available from it and stay `None`.
    """

    meeting_id: str
    status: str
    platform: str | None = None
    meeting_url: str | None = None
    title: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    custom_attributes: dict[str, Any] | None = None


class TranscriptSegment(BaseModel):
    text: str
    speaker: str | None = None
    start_time: float | None = None
    end_time: float | None = None


class Transcript(BaseModel):
    meeting_id: str
    segments: list[TranscriptSegment]


class BotDispatchResult(BaseModel):
    bot_id: str
    meeting_id: str
    status: str
    transcript_id: str | None = None
    """Set by MeetStream when a post-call transcription provider was configured."""


class MeetingActionResult(BaseModel):
    meeting_id: str
    action: str
    status: str
    detail: str | None = None


def _bot_path(bot_id: str, endpoint: str) -> str:
    """`/bots/<bot_id>/<endpoint>`, with the id URL-encoded.

    Ids often come from an LLM tool call; encoding keeps an id like `abc/remove_bot#` from
    turning a read into a different MeetStream call.
    """
    return f"/bots/{quote(str(bot_id), safe='')}/{endpoint}"


def infer_platform(meeting_url: str | None) -> str | None:
    """`"google_meet"`, `"zoom"` or `"teams"` from a meeting URL's host, else `None`."""
    if not meeting_url:
        return None
    host = urlparse(meeting_url).netloc.lower()
    for known, platform in _PLATFORM_HOSTS.items():
        if known in host:
            return platform
    return None


def transcript_config(provider: str | None, options: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The `recording_config.transcript` block for `provider`, or `None` to request no transcript.

    MeetStream takes exactly one provider key, e.g. `{"provider": {"deepgram": {"model": "nova-3"}}}`.
    Options left out use the provider's own defaults.
    """
    if provider is None:
        return None
    opts = dict(_DEFAULT_PROVIDER_OPTIONS.get(provider, {}) if options is None else options)
    return {"provider": {provider: opts}}


class MeetStreamClient:
    """Synchronous client for MeetStream's REST API.

    Example:
        ```python
        from llama_index_meetstream import MeetStreamClient

        client = MeetStreamClient(api_key="...")               # or set MEETSTREAM_API_KEY
        bot = client.dispatch_bot("https://meet.google.com/abc-defg-hij")
        transcript = client.get_transcript(bot.meeting_id)      # once the meeting has ended
        ```

    Args:
        api_key: Your MeetStream API key. Defaults to `MEETSTREAM_API_KEY`.
        base_url: MeetStream's API root. Defaults to `MEETSTREAM_BASE_URL`, then
            `https://api.meetstream.ai/api/v1`.
        timeout: Seconds before a request gives up.
        transcription_provider: Provider used by `dispatch_bot` (and the dispatch tool)
            unless a call names its own. Defaults to `"meetstream"`; `None` dispatches
            bots without post-call transcription. See `TRANSCRIPTION_PROVIDERS`.
        transcription_options: Options for that provider, e.g. `{"model": "nova-3", "language": "en"}`
            for Deepgram. Omit to use the provider's defaults.
        transport: An `httpx` transport, for tests.

    Synchronous because `BaseReader.lazy_load_data()` and `FunctionTool` functions are
    synchronous entry points; LlamaIndex's async variants (`aload_data`, `acall`) wrap them.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        *,
        transcription_provider: str | None = DEFAULT_TRANSCRIPTION_PROVIDER,
        transcription_options: dict[str, Any] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_api_key = api_key or os.environ.get("MEETSTREAM_API_KEY")
        if not resolved_api_key:
            raise ValueError(
                "MeetStream API key is required. Pass api_key=... or set the MEETSTREAM_API_KEY environment variable."
            )
        resolved_base_url = base_url or os.environ.get("MEETSTREAM_BASE_URL") or DEFAULT_BASE_URL
        self.transcription_provider = transcription_provider
        self.transcription_options = transcription_options
        # Meeting URLs of bots this client dispatched, so get_meeting can report them.
        self._meeting_urls: dict[str, str] = {}
        # MeetStream's REST API wants the literal word "Token", not "Bearer".
        self._http = httpx.Client(
            base_url=resolved_base_url.rstrip("/"),
            headers={"Authorization": f"Token {resolved_api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> MeetStreamClient:  # noqa: PYI034 -- `Self` needs 3.11+; this package supports 3.10.
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------ transport

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        retry_statuses: frozenset[int] = _RETRY_STATUSES,
    ) -> httpx.Response:
        """Send a request, making up to `_MAX_ATTEMPTS` attempts while the status is in `retry_statuses`."""
        attempts = _MAX_ATTEMPTS if retry_statuses else 1
        for attempt in range(attempts):
            try:
                response = self._http.request(method, path, json=json)
            except httpx.TimeoutException as exc:
                raise MeetStreamConnectionError(f"MeetStream did not respond to {method} {path} in time") from exc
            except httpx.RequestError as exc:
                raise MeetStreamConnectionError(f"Could not reach MeetStream at {self._http.base_url}: {exc}") from exc
            if response.status_code in retry_statuses and attempt < attempts - 1:
                delay = _RETRY_BASE_DELAY_SECONDS * (2**attempt)
                logger.warning("MeetStream %s %s returned %d; retrying in %.1fs", method, path, response.status_code, delay)
                time.sleep(delay)
                continue
            return response
        return response

    @staticmethod
    def _message(response: httpx.Response, fallback: str) -> str:
        try:
            body = response.json()
        except ValueError:
            return fallback
        if isinstance(body, dict) and isinstance(body.get("message"), str) and body["message"].strip():
            return body["message"]
        return fallback

    def _raise_for_status(self, response: httpx.Response, *, what: str, not_found: str = "meeting_not_found") -> None:
        """Turn a MeetStream error status into `MeetStreamAPIError` with a stable `code`."""
        status = response.status_code
        if status < 400:
            return
        if status == 401:
            code, default = "authentication_failed", "MeetStream rejected the API key"
        elif status == 403:
            code, default = "forbidden", f"{what}: the bot belongs to another MeetStream account, or the key lacks access"
        elif status == 404:
            code, default = not_found, f"{what}: not found"
        elif status == 429:
            code, default = "rate_limited", f"{what}: MeetStream rate limit reached; retry shortly"
        elif status >= 500:
            code, default = "upstream_error", f"{what}: MeetStream returned HTTP {status}"
        else:
            code, default = "invalid_request", f"{what}: MeetStream rejected the request (HTTP {status})"
        raise MeetStreamAPIError(self._message(response, default), code=code, status_code=status)

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        """The decoded body, or `None` if it's empty or not JSON."""
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    # ------------------------------------------------------------------ bots

    def dispatch_bot(
        self,
        meeting_url: str,
        bot_name: str = "MeetStream Bot",
        *,
        transcription_provider: str | None = _UNSET,
        transcription_options: dict[str, Any] | None = None,
    ) -> BotDispatchResult:
        """Send a bot into a meeting (`POST /bots/create_bot`).

        Args:
            meeting_url: A Google Meet, Zoom or Teams link.
            bot_name: The bot's display name in the meeting.
            transcription_provider: Post-call transcription provider for this bot. Defaults to
                the client's `transcription_provider` (`"meetstream"` unless you changed it).
                `None` records without a transcript.
            transcription_options: Provider options; defaults to the client's options when the
                provider is the client's, else the provider's own defaults.

        Not retried: repeating a create request whose response was lost could put a
        second bot in the meeting.
        """
        if transcription_provider is _UNSET:
            provider, options = self.transcription_provider, transcription_options or self.transcription_options
        else:
            provider, options = transcription_provider, transcription_options
        payload: dict[str, Any] = {"meeting_link": meeting_url, "bot_name": bot_name}
        transcript = transcript_config(provider, options)
        if transcript is not None:
            payload["recording_config"] = {"transcript": transcript}

        response = self._request("POST", "/bots/create_bot", json=payload, retry_statuses=frozenset())
        if response.status_code in (400, 422):
            raise MeetStreamAPIError(
                self._message(response, "MeetStream rejected the meeting link or bot settings"),
                code="invalid_meeting_url",
                status_code=response.status_code,
            )
        self._raise_for_status(response, what="create_bot")
        raw = self._json(response) or {}
        bot_id = raw.get("bot_id") if isinstance(raw, dict) else None
        if not bot_id:
            raise MeetStreamAPIError(
                "MeetStream accepted create_bot but returned no bot_id", code="upstream_error", status_code=response.status_code
            )
        self._meeting_urls[bot_id] = raw.get("meeting_url") or meeting_url
        return BotDispatchResult(
            bot_id=bot_id, meeting_id=bot_id, status=raw.get("status") or "unknown", transcript_id=raw.get("transcript_id")
        )

    def get_meeting(self, meeting_id: str) -> MeetingMetadata:
        """The bot's current status (`GET /bots/{bot_id}/status`)."""
        response = self._request("GET", _bot_path(meeting_id, "status"))
        self._raise_for_status(response, what=f"meeting {meeting_id}")
        raw = self._json(response) or {}
        meeting_url = self._meeting_urls.get(meeting_id)
        return MeetingMetadata(
            meeting_id=meeting_id,
            status=raw.get("status") or "unknown",
            platform=infer_platform(meeting_url),
            meeting_url=meeting_url,
            custom_attributes=raw.get("custom_attributes") or None,
        )

    # ------------------------------------------------------------------ transcripts

    def get_transcript(self, meeting_id: str) -> Transcript:
        """The post-call transcript (`GET /bots/{bot_id}/get_transcript`).

        Raises `MeetStreamAPIError` with `code`:
          - `"transcript_not_ready"` (HTTP 202): still processing; try again later.
          - `"transcript_unavailable"`: transcription wasn't enabled, the bot was never
            admitted (409), or processing failed (422). Retrying won't help.
          - `"meeting_not_found"` (404): no such bot, or no transcript exists for it.
        """
        response = self._request("GET", _bot_path(meeting_id, "get_transcript"))
        if response.status_code == 202:
            raise MeetStreamAPIError(
                self._message(response, f"Transcript for {meeting_id} is still processing"),
                code="transcript_not_ready",
                status_code=202,
            )
        if response.status_code in (409, 422):
            raise MeetStreamAPIError(
                self._message(response, f"No transcript will be produced for {meeting_id}"),
                code="transcript_unavailable",
                status_code=response.status_code,
            )
        self._raise_for_status(response, what=f"transcript for {meeting_id}")
        return Transcript(meeting_id=meeting_id, segments=parse_transcript(self._json(response)))

    # ------------------------------------------------------------------ in-meeting actions

    def _action(
        self,
        meeting_id: str,
        action: str,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        retry_statuses: frozenset[int] = _RETRY_STATUSES,
    ) -> MeetingActionResult:
        response = self._request(method, path, json=json, retry_statuses=retry_statuses)
        if response.status_code == 409:
            raise MeetStreamAPIError(
                self._message(response, f"The bot for {meeting_id} is not currently in a meeting"),
                code="meeting_not_active",
                status_code=409,
            )
        self._raise_for_status(response, what=f"{action} for {meeting_id}")
        raw = self._json(response) or {}
        detail = raw.get("status") if isinstance(raw, dict) else None
        return MeetingActionResult(meeting_id=meeting_id, action=action, status="ok", detail=detail)

    def send_chat_message(self, meeting_id: str, message: str) -> MeetingActionResult:
        """Post `message` (1-2000 characters) into the meeting chat."""
        return self._action(
            meeting_id,
            "send_chat_message",
            "POST",
            _bot_path(meeting_id, "send_message"),
            {"message": message},
            retry_statuses=_COMMAND_RETRY_STATUSES,
        )

    def send_image(self, meeting_id: str, image_url: str, display_duration_seconds: float | None = None) -> MeetingActionResult:
        """Show the image at `image_url` (HTTPS, publicly reachable) as the bot's video feed."""
        payload: dict[str, Any] = {"img_url": image_url}
        if display_duration_seconds is not None:
            payload["display_duration"] = display_duration_seconds
        return self._action(
            meeting_id, "send_image", "POST", _bot_path(meeting_id, "send_image"), payload, retry_statuses=_COMMAND_RETRY_STATUSES
        )

    def leave_meeting(self, meeting_id: str) -> MeetingActionResult:
        """Make the bot leave (`GET /bots/{bot_id}/remove_bot`). Recorded data is kept."""
        return self._action(meeting_id, "leave_meeting", "GET", _bot_path(meeting_id, "remove_bot"))

    def perform_meeting_action(
        self, meeting_id: str, action: Literal["send_chat_message", "send_image", "leave_meeting"], **payload: Any
    ) -> MeetingActionResult:
        """Run an in-meeting action by name, for callers that only have `action` as a string."""
        if action == "send_chat_message":
            return self.send_chat_message(meeting_id, payload["message"])
        if action == "send_image":
            return self.send_image(meeting_id, payload["image_url"], payload.get("display_duration_seconds"))
        if action == "leave_meeting":
            return self.leave_meeting(meeting_id)
        raise ValueError(f"Unsupported meeting action: {action!r}")


# ---------------------------------------------------------------------- transcript parsing


def _num(item: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, dict):  # V2 timestamps: {"relative": 1.2, "absolute": ...}
            value = value.get("relative")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _speaker(item: dict[str, Any]) -> str | None:
    participant = item.get("participant")
    name = (
        item.get("speaker_name")
        or (participant.get("name") if isinstance(participant, dict) else None)
        or item.get("speaker")
    )
    if isinstance(name, bool) or name is None or name == "":
        return None
    if isinstance(name, int):  # some providers number speakers from 0
        return f"Speaker {name + 1}"
    return str(name)


def _words_text(words: list[Any]) -> str:
    parts = []
    for word in words:
        if isinstance(word, dict):
            text = word.get("punctuated_word") or word.get("text") or word.get("word")
            if text:
                parts.append(str(text))
    return " ".join(parts)


def _segment(item: Any) -> TranscriptSegment | None:
    if isinstance(item, str):
        return TranscriptSegment(text=item.strip()) if item.strip() else None
    if not isinstance(item, dict):
        return None
    words = item.get("words") if isinstance(item.get("words"), list) else []
    text = item.get("transcript") or item.get("text") or _words_text(words)
    if not isinstance(text, str) or not text.strip():
        return None
    start = _num(item, "start_time", "start")
    end = _num(item, "end_time", "end")
    word_dicts = [w for w in words if isinstance(w, dict)]
    if start is None and word_dicts:
        start = _num(word_dicts[0], "start", "start_timestamp")
    if end is None and word_dicts:
        end = _num(word_dicts[-1], "end", "end_timestamp")
    return TranscriptSegment(text=text.strip(), speaker=_speaker(item), start_time=start, end_time=end)


def parse_transcript(content: Any) -> list[TranscriptSegment]:
    """Segments from either of MeetStream's formatted transcript shapes.

    - Segment list: `[{"speaker", "transcript", "start_time", "end_time", "words"}]`
    - Participant-keyed (V2): `[{"participant": {"name"}, "words": [{"text", "start_timestamp": {"relative"}}]}]`

    A list wrapped in an object under `segments`, `transcript`, `utterances` or `results`
    is accepted too. Items without text are skipped; a body with no recognisable list
    raises `MeetStreamAPIError` (`code="transcript_format_error"`).
    """
    items = content
    if isinstance(content, dict):
        items = next(
            (content[k] for k in ("segments", "transcript", "utterances", "results") if isinstance(content.get(k), list)),
            None,
        )
    if not isinstance(items, list):
        raise MeetStreamAPIError(
            "MeetStream returned a transcript in an unrecognised format", code="transcript_format_error", status_code=200
        )
    segments = []
    for index, item in enumerate(items):
        segment = _segment(item)
        if segment is None:
            logger.warning("Skipping transcript item %d: no text", index)
            continue
        segments.append(segment)
    return segments
