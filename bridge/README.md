# meetstream-bridge

A normalized FastAPI HTTP bridge between the real MeetStream REST API and
this repository's LangChain/LlamaIndex integrations. See
[`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) and
[`../docs/BRIDGE_SERVER.md`](../docs/BRIDGE_SERVER.md) for the full design
rationale; this file only covers running it.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/bots` | Dispatch a MeetStream bot into a meeting |
| `GET` | `/meetings/{meeting_id}` | Normalized meeting/bot metadata |
| `GET` | `/meetings/{meeting_id}/transcript` | Normalized transcript segments |
| `POST` | `/meetings/{meeting_id}/actions` | Perform a supported in-meeting action |
| `GET` | `/health` | Liveness check (does not call MeetStream) |

## Run locally

```bash
cd bridge
pip install -e ".[dev]"
export MEETSTREAM_API_KEY=your-real-key
uvicorn app.main:app --reload
```

Interactive API docs: http://localhost:8000/docs

## Test

```bash
cd bridge
pytest
```

Every test mocks MeetStream at the `httpx` transport layer with `respx` --
none make a real network call, and none require `MEETSTREAM_API_KEY` to be a
real key (`tests/conftest.py` sets a placeholder).

## Environment variables

| Variable | Required | Default |
|---|---|---|
| `MEETSTREAM_API_KEY` | Yes | none |
| `MEETSTREAM_BASE_URL` | No | `https://api.meetstream.ai/api/v1` |
| `MEETSTREAM_REQUEST_TIMEOUT_SECONDS` | No | `30.0` |
