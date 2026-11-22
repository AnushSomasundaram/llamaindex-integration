# Architecture

## Shape

```
LlamaIndex app
   │  MeetStreamReader, get_meetstream_tools(client)
   ▼
llama_index_meetstream.MeetStreamClient    (sync httpx client, one connection pool)
   │  Authorization: Token <MEETSTREAM_API_KEY>
   ▼
https://api.meetstream.ai/api/v1
```

| Module | Role |
|---|---|
| `client.py` | The only module that makes HTTP calls. Owns MeetStream's paths, auth header, error mapping, retries and transcript parsing. |
| `readers/meetstream.py` | `MeetStreamReader`: transcript segments → `Document`s. |
| `tools/` | Six `FunctionTool`s, each a thin wrapper over one client method. |
| `exceptions.py` | `MeetStreamAPIError` (with a stable `code`) and `MeetStreamConnectionError`. |

The package calls MeetStream directly. The key stays in the process that uses the package
and is sent only to MeetStream. There is no intermediate server to deploy or secure.

## MeetStream endpoints used

All from MeetStream's [API reference](https://docs.meetstream.ai/api-reference).

| Client method | Endpoint | Notes |
|---|---|---|
| `dispatch_bot` | `POST /bots/create_bot` | Sends `meeting_link`, `bot_name` and `recording_config.transcript.provider`. Not retried, so a lost response can't put two bots in a meeting. |
| `get_meeting` | `GET /bots/{bot_id}/status` | Returns `status` and `custom_attributes`. |
| `get_transcript` | `GET /bots/{bot_id}/get_transcript` | Resolves the bot's transcript for us. 202 = still processing, 409 = transcription not enabled or bot not admitted, 422 = processing failed. |
| `send_chat_message` | `POST /bots/{bot_id}/send_message` | `{"message"}`, 1–2000 characters. |
| `send_image` | `POST /bots/{bot_id}/send_image` | `{"img_url", "display_duration"}`. |
| `leave_meeting` | `GET /bots/{bot_id}/remove_bot` | GET, not DELETE. 202 while stopping, 200 once stopped. |

`meeting_id` throughout is MeetStream's `bot_id`: MeetStream has no separate meeting id.

## Transcription provider

`create_bot` takes one post-call provider under `recording_config.transcript.provider`, as
`{"<provider>": {options}}`. The client defaults to `{"meetstream": {"language": "auto"}}`
(MeetStream's own engine). Developers can pick another on the client or per call, or pass
`None` for no transcript. The dispatch tool doesn't expose the choice to the model.

## Transcripts

`get_transcript` returns one of MeetStream's formatted shapes, and `parse_transcript`
accepts both:

- **Segment list:** `[{"speaker", "transcript", "start_time", "end_time", "words"}]`
- **Participant-keyed:** `[{"participant": {"name"}, "words": [{"text", "start_timestamp": {"relative"}, ...}]}]`

The text and times of participant-keyed items come from their words. Numeric speakers become
`"Speaker N"`. Items with no text are skipped with a warning. A body with no recognisable
list raises `transcript_format_error`, so the package never makes up segments.

The reader emits one `Document` per segment (speaker turn), so retrieval can return the
specific turn that answers a question, with speaker and times attached. It doesn't
pre-chunk; LlamaIndex's node parsers split further if needed.

## Errors and retries

HTTP statuses map to `MeetStreamAPIError.code` values (see `exceptions.py`). MeetStream's
`message` field is used as the exception text when it has one. Reads and `remove_bot` make up
to three attempts on 500/502/503/504, with exponential backoff. Chat messages and images are
retried only on 503 (MeetStream's "command channel not connected yet"), because after a 500
the message may already have been posted. `create_bot` is never retried. Network failures and timeouts raise `MeetStreamConnectionError`.

## Sync, not async

`BaseReader.lazy_load_data()` and `FunctionTool` functions are synchronous entry points,
and so is the common notebook and script use case. LlamaIndex's async variants
(`aload_data`, `acall`) wrap them, so async agents work unchanged.

## Why a standalone package

It's installable on its own (`llama-index-meetstream`) and versioned with MeetStream's API
rather than LlamaIndex's release cycle. It depends only on `llama-index-core`, `httpx` and
`pydantic`.

## Limitations

- MeetStream's status endpoint doesn't return a meeting title or start/end times.
- `platform`/`meeting_url` are remembered only for bots the same client dispatched.
- No webhook handling. Callers poll until the transcript is ready.
