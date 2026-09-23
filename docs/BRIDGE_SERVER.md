# Bridge Server

The bridge (`bridge/`) is a small FastAPI service that is the *only* thing in this
repository that talks to MeetStream's real REST API. Both `langchain-meetstream` and
`llama-index-meetstream` talk to the bridge over HTTP, never to MeetStream directly.

It is **not** LangChain and **not** LlamaIndex — it has no dependency on either framework
(`bridge/pyproject.toml` lists neither). It exists purely to give both framework
integrations one shared, already-normalized MeetStream contract, so a MeetStream API
change is a one-file fix here instead of a hunt through two packages.

```
               MeetStream API
                     ▲
                     │
              Bridge Server
                /         \
               /           \
        LangChain       LlamaIndex
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design rationale, including exactly
which MeetStream endpoints this bridge's assumptions came from.

## Running it

```bash
cd bridge
pip install -e ".[dev]"
export MEETSTREAM_API_KEY=your-real-key
uvicorn app.main:app --reload
```

Interactive docs at `http://localhost:8000/docs`. Health check: `GET /health` (does not
call MeetStream — see `app/main.py`'s docstring for why).

## Endpoints

### `POST /bots` — dispatch a bot

```json
// Request
{"meeting_url": "https://meet.google.com/abc-defg-hij", "bot_name": "MeetStream Bot"}

// Response
{"bot_id": "bot_123", "meeting_id": "bot_123", "status": "Active"}
```

`meeting_id` in every bridge response *is* MeetStream's `bot_id` — MeetStream has no
independent meeting identifier; see `ARCHITECTURE.md` §6. `status` is whatever MeetStream
itself reports (e.g. `"Active"` right after dispatch, then observed to progress through
`"Joining"` → `"InWaitingRoom"` → `"InMeeting"` → `"MediaProcessing"` after leaving, in a
real live-tested run — see `ARCHITECTURE.md` §3), not remapped to an invented enum.

### `GET /meetings/{meeting_id}` — meeting metadata

```json
{
  "meeting_id": "bot_123",
  "status": "InMeeting",
  "platform": "google_meet",
  "meeting_url": null,
  "title": null,
  "started_at": null,
  "ended_at": null,
  "custom_attributes": {}
}
```

`title`, `started_at`, `ended_at`, and usually `meeting_url`/`platform` are `null` —
**not a bug**. See `ARCHITECTURE.md` §6 for exactly why each of these fields is, or isn't,
recoverable from MeetStream's real API.

### `GET /meetings/{meeting_id}/transcript` — transcript

```json
{
  "meeting_id": "bot_123",
  "segments": [
    {"text": "Engineering should finish this Friday.", "speaker": "Sarah", "start_time": 14.2, "end_time": 18.6}
  ]
}
```

Segments are speaker turns, in order — the bridge does not further chunk them (see
`ARCHITECTURE.md` §7). Can raise `transcript_not_ready` (still processing — retry later) or
`transcript_unavailable` (never will exist, or processing failed).

### `POST /meetings/{meeting_id}/actions` — perform an action

```json
// send_meeting_chat_message
{"action": "send_chat_message", "payload": {"message": "Standup starting now"}}

// send_meeting_image
{"action": "send_image", "payload": {"image_url": "https://example.com/slide.png", "display_duration_seconds": 10}}

// leave_meeting
{"action": "leave_meeting"}
```

```json
// Response (shape identical for every action)
{"meeting_id": "bot_123", "action": "send_chat_message", "status": "ok", "detail": "sent"}
```

Only these three actions are exposed because only these three were confirmed real and
working against MeetStream's live API by the reference implementations this project was
built from — see `ARCHITECTURE.md` §3. No other MeetStream capability is exposed as an
"action" here without that same confirmation.

### `GET /health`

```json
{"status": "ok"}
```

## Error model

Every error is `{"error": {"code": "...", "message": "..."}}` with a matching HTTP status:

| `code` | HTTP status | Meaning |
|---|---|---|
| `authentication_failed` | 401 | MeetStream rejected the configured API key |
| `meeting_not_found` | 404 | No such meeting/bot |
| `bot_not_found` | 404 | (Internal — surfaces as `meeting_not_found` on meeting-scoped routes) |
| `invalid_meeting_url` | 422 | MeetStream rejected the meeting URL |
| `unsupported_platform` | 422 | Meeting platform not supported |
| `transcript_not_ready` | 409 | Transcript still processing |
| `transcript_unavailable` | 404 | No transcript exists / will exist |
| `transcript_format_error` | 502 | Downloaded transcript didn't match a recognized shape |
| `unsupported_action` | 422 | Requested action isn't one of the three real ones, or its payload didn't validate |
| `upstream_error` | 502 | Unmapped MeetStream error |
| `upstream_timeout` | 504 | MeetStream didn't respond in time |

No response body, log line, or exception ever includes the configured MeetStream API key,
an `Authorization` header value, or a raw upstream response body — see
`app/main.py::handle_bridge_error` and `app/clients/meetstream.py`.

## MeetStream API assumptions (read before changing `app/clients/meetstream.py`)

Summarized from `ARCHITECTURE.md` §3 — full detail lives there:

- Auth: `Authorization: Token <api_key>` (the literal word "Token").
- `POST /bots/create_bot`, `GET /bots/{id}/status`, `GET /bots/{id}/remove_bot` (GET, not
  DELETE), `POST /bots/{id}/send_message`, `POST /bots/{id}/send_image`,
  `GET /bots/{id}/transcriptions` — all confirmed by two independent, live-tested local
  reference implementations.
- `recording_config.transcript.provider.deepgram` must be set on `create_bot` for a
  transcript to be produced at all — confirmed working by one reference implementation.
- The downloaded transcript file's internal JSON schema is **not** confirmed
  byte-for-byte by any available source; `app/services/transcript_service.py` parses it
  defensively and raises `TranscriptFormatError` rather than guessing.
- No MeetStream endpoint returns a meeting title or join/leave timestamps by ID.

If you're extending this bridge with a new MeetStream capability, look for it in an actual
tested client first (this repository's history, or a fresh capture against MeetStream's
real API) rather than reading it off documentation alone — this project was built after
finding that MeetStream's own docs and its real, live-tested behavior had already diverged
in small ways (the `audio_required` field, the exact `recording_config` nesting) across the
reference implementations this bridge was built from.
