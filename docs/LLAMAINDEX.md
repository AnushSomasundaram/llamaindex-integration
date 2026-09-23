# LlamaIndex Guide

`llama_index_meetstream` — native LlamaIndex integration for MeetStream. This guide covers
usage; see [`ARCHITECTURE.md`](ARCHITECTURE.md) for design rationale and the root
[`README.md`](../README.md) for a quick reference.

## Install

```bash
pip install -e .              # core package (run from the repo root)
pip install -e ".[examples]"  # + example-script deps
```

Requires a running [bridge server](BRIDGE_SERVER.md) and Python 3.10+. Verified against
`llama-index-core==0.14.24` (see [`ARCHITECTURE.md`](ARCHITECTURE.md) §13).

## The client

```python
from llama_index_meetstream import MeetStreamClient

client = MeetStreamClient(api_key="...", base_url="http://localhost:8000")
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) §8a for what `api_key` means here (sent to the
bridge, not MeetStream directly). Shared internally between `MeetStreamReader` and every
tool.

## Loading transcripts: `MeetStreamReader`

```python
from llama_index_meetstream import MeetStreamReader

reader = MeetStreamReader(meeting_id="meeting_123", api_key="...")
documents = reader.load_data()       # eager — list[Document]
for doc in reader.lazy_load_data():  # or lazily
    ...
```

A LlamaIndex `Document` is `text` plus `metadata`. Like the LangChain loader, this reader
emits **one `Document` per transcript segment**, with identical metadata fields (`source`,
`meeting_id`, `meeting_title`, `platform`, `speaker`, `start_time`, `end_time`) — the two
frameworks' packages are kept semantically identical on purpose, so a meeting looks the
same regardless of which framework you're using.

Async: `reader.aload_data()` works via `BaseReader`'s default thread-executor wrapping —
see [`ARCHITECTURE.md`](ARCHITECTURE.md) §11.

## Tools: `get_meetstream_tools`

```python
from llama_index_meetstream import MeetStreamClient
from llama_index_meetstream.tools import get_meetstream_tools

client = MeetStreamClient(api_key="...")
tools = get_meetstream_tools(client)   # list[FunctionTool], 6 tools
```

Built with `llama_index.core.tools.FunctionTool` — the current recommended way to expose a
plain function as an LlamaIndex tool. There is **no** separate "MeetStream agent" class;
`tools` works with any LlamaIndex agent:

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI

agent = FunctionAgent(tools=tools, llm=OpenAI(model="gpt-4o-mini"))
response = await agent.run(user_msg="...")
```

## RAG

`examples/rag_example.py`:

```
MeetStream → MeetStreamReader → Documents → VectorStoreIndex → Query Engine
```

Run:

```bash
pip install -e ".[examples]"
python examples/rag_example.py meeting_123 "What deadline was discussed?"
```

## Errors

```python
from llama_index_meetstream import MeetStreamAPIError

try:
    transcript = client.get_transcript("meeting_123")
except MeetStreamAPIError as exc:
    print(exc.code, str(exc))
```

Full code list: [`BRIDGE_SERVER.md`](BRIDGE_SERVER.md#error-model).

## Examples

| File | Demonstrates |
|---|---|
| `examples/reader_example.py` | Basic `MeetStreamReader` usage |
| `examples/rag_example.py` | Full RAG pipeline over a transcript |
| `examples/agent_example.py` | A `FunctionAgent` dispatching a bot and reading a transcript |
