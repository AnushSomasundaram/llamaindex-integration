# MeetStream AI LlamaIndex Integration

A native [LlamaIndex](https://www.llamaindex.ai) integration for
[MeetStream](https://meetstream.ai), the API that sends bots into Google Meet, Zoom and
Microsoft Teams meetings to record and transcribe them.

It works in both directions:

- **Meeting → AI app.** `MeetStreamReader` loads a meeting transcript as LlamaIndex
  `Document`s (one per speaker turn), ready for indexing and querying.
- **AI app → meeting.** `get_meetstream_tools(client)` gives any LlamaIndex agent six
  `FunctionTool`s: send a bot to a meeting, check its status, read the transcript, post in
  the chat, show an image, and leave.

```
Your LlamaIndex app ──► llama-index-meetstream ──► MeetStream REST API ──► Meet / Zoom / Teams
```

The package calls MeetStream's REST API directly with your API key. There is no server to run.

## Install

```bash
pip install -e .              # from the repository root
pip install -e ".[examples]"  # plus what the example scripts need
```

Python 3.10+, `llama-index-core` 0.14, and a MeetStream API key (from the
[MeetStream dashboard](https://app.meetstream.ai)).

## Configure

```bash
export MEETSTREAM_API_KEY=...        # or pass api_key=... to MeetStreamClient / MeetStreamReader
```

| Variable | Purpose |
|---|---|
| `MEETSTREAM_API_KEY` | Your MeetStream key. Sent only to MeetStream, as `Authorization: Token <key>`. |
| `MEETSTREAM_BASE_URL` | Optional. Defaults to `https://api.meetstream.ai/api/v1`. |
| `OPENAI_API_KEY` | Only for the RAG and agent examples. The package itself doesn't use it. |

## Quick start

```python
from llama_index_meetstream import MeetStreamReader

documents = MeetStreamReader(meeting_id="<bot id>").load_data()
```

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI
from llama_index_meetstream import MeetStreamClient
from llama_index_meetstream.tools import get_meetstream_tools

client = MeetStreamClient()
agent = FunctionAgent(tools=get_meetstream_tools(client), llm=OpenAI(model="gpt-4o-mini"))
```

`meeting_id` is MeetStream's `bot_id`: the id `dispatch_bot` returns, or the one shown in
the MeetStream dashboard.

## Choosing a transcription provider

Bots are transcribed after the call by **MeetStream's own transcription** unless you choose
another provider. Set it once on the client (it then applies to `dispatch_bot` and the
dispatch tool) or per call:

```python
client = MeetStreamClient(transcription_provider="deepgram", transcription_options={"model": "nova-3", "language": "en"})

client.dispatch_bot("https://zoom.us/j/123", transcription_provider="assemblyai")
client.dispatch_bot("https://zoom.us/j/123", transcription_provider=None)   # no transcript
```

Post-call providers MeetStream documents: `meetstream` (default), `deepgram`, `assemblyai`,
`jigsawstack`, `sarvam`, `smallest`, `meeting_captions` (also in `TRANSCRIPTION_PROVIDERS`).
Options left out use the provider's defaults; see MeetStream's
[Create Bot reference](https://docs.meetstream.ai/api-reference/api-endpoints/bot-endpoints/create-bot).
The provider is a developer setting: agents can't change it through the dispatch tool.

## Transcript metadata

Each `Document` carries:

| Field | Type | Notes |
|---|---|---|
| `source` | `str` | Always `"meetstream"`. |
| `meeting_id` | `str` | MeetStream's `bot_id`. |
| `meeting_title` | `str \| None` | MeetStream's status endpoint doesn't return a title, so this is `None`. |
| `platform` | `str \| None` | `"google_meet"` / `"zoom"` / `"teams"`, when the same client dispatched the bot. |
| `speaker` | `str \| None` | `None` if the provider didn't identify the speaker. |
| `start_time` / `end_time` | `float \| None` | Seconds from the start of the recording. |

## Errors

Everything raises `MeetStreamAPIError` with a stable `.code`, or `MeetStreamConnectionError`
if MeetStream couldn't be reached. The codes are listed in
[`llama_index_meetstream/exceptions.py`](llama_index_meetstream/exceptions.py). The ones you'll
see most:

| `code` | Meaning |
|---|---|
| `transcript_not_ready` | MeetStream is still processing (HTTP 202). Try again shortly. |
| `transcript_unavailable` | Transcription wasn't enabled, the bot was never admitted, or processing failed. |
| `meeting_not_found` | No bot with that id. |
| `authentication_failed` | MeetStream rejected the API key. |
| `meeting_not_active` | A chat/image/leave action while the bot isn't in a meeting. |

## Examples

| File | Shows |
|---|---|
| [`examples/reader_example.py`](examples/reader_example.py) | Loading a transcript |
| [`examples/rag_example.py`](examples/rag_example.py) | `VectorStoreIndex` + query engine over a transcript |
| [`examples/agent_example.py`](examples/agent_example.py) | A `FunctionAgent` that dispatches a bot and reads a transcript |
| [`notebooks/walkthrough.ipynb`](notebooks/walkthrough.ipynb) | Every feature, step by step, against your own account |

## Documentation

- [`docs/LLAMAINDEX.md`](docs/LLAMAINDEX.md): usage guide
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): design and the MeetStream endpoints used
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md): tests, linting, building

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check llama_index_meetstream tests examples
```

Tests mock MeetStream at the HTTP layer with `respx`; no network or key is needed.

## Known limitations

- **No meeting title or start/end times.** MeetStream's status endpoint returns only the
  bot's status and custom attributes.
- **`platform` and `meeting_url` are known only to the client that dispatched the bot.** A
  fresh client looking up an existing bot gets `None` for both.
- **No webhooks.** Poll `get_meeting_transcript` (or `reader.load_data()`) until it stops
  raising `transcript_not_ready`.
