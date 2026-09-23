# MeetStream AI LlamaIndex Integration

A native [LlamaIndex](https://docs.llamaindex.ai) integration for [MeetStream](https://meetstream.ai)
— a service that sends bots into video meetings (Google Meet, Zoom, Microsoft Teams) to record
and transcribe them.

## What this project does

MeetStream supplies meeting infrastructure: send a bot into a meeting, get back a
transcript. LlamaIndex is an AI application framework: it defines how an LLM reads documents
(for retrieval/RAG) and calls tools (for agents).

Without this project, using MeetStream from a LlamaIndex application means hand-writing REST
calls to MeetStream and hand-converting its JSON responses into `Document` objects and tool
functions yourself. This project does that conversion for you, in both directions:

**Meeting data → AI application** (a document reader):

```
Google Meet / Zoom / Teams
          ↓
      MeetStream
          ↓
      Bridge Server
          ↓
      Document Reader
          ↓
       LlamaIndex
          ↓
    RAG / Search / QA
```

**AI application → Meeting** (agent tools):

```
User
  ↓
AI Agent
  ↓
MeetStream Tool
  ↓
Bridge Server
  ↓
MeetStream
  ↓
Meeting
```

Concretely, this repository ships two things:

1. **A bridge server** (`bridge/`) — the only thing that talks to MeetStream's real API.
2. **`llama-index-meetstream`** (repo root) — a `MeetStreamReader` and a set of agent tools
   for LlamaIndex.

This is a standalone, independently-installable package — not a contribution into the
LlamaIndex repository itself (see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §2 for why).

## The bridge server

The bridge server is **not** LlamaIndex. It's a MeetStream-specific API adapter that sits
between LlamaIndex and MeetStream:

```
       MeetStream API
             ▲
             │
      Bridge Server
             │
        LlamaIndex
```

It exists because:

- it prevents duplicating MeetStream-specific logic across multiple frameworks/languages;
- it standardizes MeetStream's responses into one normalized shape;
- it centralizes authentication to MeetStream (the real API key lives only here);
- it centralizes validation and error mapping into one consistent error taxonomy;
- it isolates the framework integration from future MeetStream API changes — a MeetStream
  endpoint rename is a one-file fix in the bridge, not a package-wide hunt.

Full endpoint reference: [`docs/BRIDGE_SERVER.md`](docs/BRIDGE_SERVER.md). Full design
rationale, including exactly which MeetStream API behavior this bridge's assumptions are
based on: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Document readers, in plain terms

A LlamaIndex `Document` is just **text + metadata**:

```python
Document(
    text="We will launch Friday.",
    metadata={"speaker": "Sarah", "meeting_id": "123"},
)
```

That's the unit LlamaIndex's retrieval (RAG) machinery is built around: embed the text,
search over it, and use the metadata to filter, cite, or display results. `MeetStreamReader`
turns a MeetStream transcript into a list of these — one per speaker turn, not one giant blob
for the whole meeting — so a search for "what's the deadline?" can return the *specific turn*
where that was said, along with who said it and when.

## Tools, in plain terms

A tool is a plain function exposed to an LLM/agent, with a description good enough that the
model can decide *when* to call it:

```
User: "Get the transcript from yesterday's meeting."
        ↓
Agent decides to call: get_meeting_transcript()
        ↓
MeetStream
```

This project does **not** build a separate "MeetStream agent." `get_meetstream_tools(client)`
returns plain `FunctionTool` objects that you pass to your *own*, already-existing agent —
giving it MeetStream capabilities, not replacing it.

## Repository layout

```
llamaindex-meetstream/
├── bridge/                          # FastAPI bridge server (no LlamaIndex deps)
│   ├── app/
│   │   ├── main.py                  # FastAPI app, lifespan, error handler wiring
│   │   ├── api/                     # HTTP routes (bots, meetings, transcripts)
│   │   ├── clients/meetstream.py    # The ONLY module that calls the real MeetStream API
│   │   ├── models/                  # Pydantic request/response models
│   │   ├── services/                # Normalization logic between client and API layer
│   │   ├── exceptions.py            # This bridge's error taxonomy
│   │   └── config.py
│   └── tests/
│
├── llama_index_meetstream/
│   ├── client.py                    # MeetStreamClient (talks to the bridge)
│   ├── readers/meetstream.py        # MeetStreamReader
│   └── tools/meetstream.py          # dispatch_bot, get_meeting, get_transcript, meeting_action
├── tests/
├── examples/{reader,rag,agent}_example.py
│
├── docs/
│   ├── ARCHITECTURE.md              # Full technical design + MeetStream API assumptions
│   ├── BRIDGE_SERVER.md             # Bridge endpoint reference
│   ├── LLAMAINDEX.md                # Usage guide
│   └── DEVELOPMENT.md               # Step-by-step dev setup
│
├── notebooks/                       # End-to-end / feature-manual walkthroughs
├── scripts/verification/            # Local + live verification scripts
├── .env.example
└── pyproject.toml
```

## Installation

The package (repo root) and the bridge each have their own `pyproject.toml` and install
independently:

```bash
pip install -e .
pip install -e bridge
```

Prerequisites: Python 3.10+, and a MeetStream API key (only the bridge needs the *real* one).

## Environment variables

```bash
cp .env.example .env
```

| Variable | Used by | Purpose |
|---|---|---|
| `MEETSTREAM_API_KEY` | bridge | The real MeetStream API key. Only the bridge process ever sends this to MeetStream. |
| `MEETSTREAM_BASE_URL` | bridge | Override if MeetStream's API isn't at the default URL. |
| `MEETSTREAM_API_KEY` | `MeetStreamClient` | Sent to the **bridge** as a bearer token — see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §8a for what this means today (not yet verified by the bridge). |
| `MEETSTREAM_BRIDGE_URL` | `MeetStreamClient` | Where the bridge is running (default `http://localhost:8000`). |
| `OPENAI_API_KEY` | example scripts only | Used by the RAG/agent examples for embeddings + chat. Not required by the package itself. |

## Authentication

- **Bridge → MeetStream**: `Authorization: Token <MEETSTREAM_API_KEY>` — confirmed against
  MeetStream's real API (see `docs/ARCHITECTURE.md` §3). Only `bridge/app/clients/meetstream.py`
  ever sends this.
- **Framework package → bridge**: `Authorization: Bearer <api_key>` — a forward-compatible
  slot for future bridge-level access control, **not yet verified by the bridge** in v0.1.
  See `docs/ARCHITECTURE.md` §8a.

## Starting the bridge

```bash
cd bridge
pip install -e ".[dev]"
export MEETSTREAM_API_KEY=your-real-key
uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs`. Full reference: [`docs/BRIDGE_SERVER.md`](docs/BRIDGE_SERVER.md).

## LlamaIndex quick start

```python
from llama_index_meetstream import MeetStreamReader

reader = MeetStreamReader(meeting_id="meeting_123", api_key="...")
documents = reader.load_data()
```

```python
from llama_index_meetstream import MeetStreamClient
from llama_index_meetstream.tools import get_meetstream_tools

client = MeetStreamClient(api_key="...")
tools = get_meetstream_tools(client)
```

Full guide: [`docs/LLAMAINDEX.md`](docs/LLAMAINDEX.md).

## Examples

| Reader | RAG | Agent |
|---|---|---|
| `examples/reader_example.py` | `examples/rag_example.py` | `examples/agent_example.py` |

## Transcript metadata format

Each segment produces this metadata:

| Field | Type | Notes |
|---|---|---|
| `source` | `str` | Always `"meetstream"`. |
| `meeting_id` | `str` | MeetStream's `bot_id` — see `docs/ARCHITECTURE.md` §6. |
| `meeting_title` | `str \| None` | Almost always `None` — MeetStream's API doesn't expose it. |
| `platform` | `str \| None` | `"google_meet"` / `"zoom"` / `"teams"`, inferred from the meeting URL when known. |
| `speaker` | `str \| None` | `None` if MeetStream couldn't identify the speaker. |
| `start_time` / `end_time` | `float \| None` | Seconds from meeting start. |

## Error handling

The package raises one exception type, `MeetStreamAPIError`, with a stable `.code` matching
the bridge's own error codes (`"meeting_not_found"`, `"transcript_not_ready"`,
`"authentication_failed"`, ...) — full list in [`docs/BRIDGE_SERVER.md`](docs/BRIDGE_SERVER.md#error-model).
`MeetStreamConnectionError` means the bridge itself couldn't be reached.

## Development setup / Testing / Package builds / Publishing

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the full step-by-step guide (clone →
venv → install → configure `.env` → run bridge → run tests → run examples → build wheel →
publish). Short version:

```bash
(cd bridge && pip install -e ".[dev]" && pytest)
(pip install -e ".[dev]" && pytest)
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ValueError: MeetStream API key is required` | Neither `api_key=` nor `MEETSTREAM_API_KEY` is set on `MeetStreamClient`/`MeetStreamReader`. |
| `MeetStreamConnectionError` | The bridge isn't running, or `MEETSTREAM_BRIDGE_URL` points at the wrong host/port. Check `curl $MEETSTREAM_BRIDGE_URL/health`. |
| `MeetStreamAPIError` with `code="authentication_failed"` | The bridge's own `MEETSTREAM_API_KEY` (the real MeetStream key) is wrong or expired — check the bridge process's environment, not the framework package's. |
| `MeetStreamAPIError` with `code="transcript_not_ready"` | MeetStream is still processing the transcript. This is expected right after a meeting ends — wait and retry; the package doesn't poll forever on your behalf. |
| `meeting_title`/`started_at`/`ended_at` are always `None` | Expected — MeetStream's API doesn't expose these. See `docs/ARCHITECTURE.md` §6. |
| `pip install -e ".[dev]"` fails with a readme error | Run it from the directory containing the relevant `pyproject.toml` (repo root for the package, `bridge/` for the bridge). |

## Known limitations

- **The bridge does not yet verify the `api_key` sent by framework clients.** It's a
  forward-compatible slot for future bridge-level access control, not yet enforced — see
  `docs/ARCHITECTURE.md` §8a. Don't expose an unauthenticated bridge to an untrusted network.
- **`meeting_title`, `started_at`, `ended_at` are almost always `None`.** MeetStream's API
  doesn't expose them synchronously; see `docs/ARCHITECTURE.md` §6.
- **No webhook ingestion.** MeetStream pushes bot lifecycle/transcription-ready events to a
  webhook; this bridge doesn't ingest them in v0.1 (it's stateless) — poll
  `get_meeting_transcript` instead. See `docs/ARCHITECTURE.md` §10.
- **No third shared package between this and a sibling `langchain-meetstream` project.** Each
  has its own small `client.py`, deliberately duplicated rather than factored into a
  confusing third published dependency for v0.1 — see `docs/ARCHITECTURE.md` §8.
- **The downloaded transcript file's exact schema isn't byte-for-byte confirmed** against
  MeetStream's real API by any source available while building this project; the bridge
  parses it defensively and raises a typed error rather than guessing — see
  `docs/ARCHITECTURE.md` §3 and §7.
