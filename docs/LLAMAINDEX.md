# LlamaIndex Guide

How to use `llama_index_meetstream`. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the design.

## Install

```bash
pip install -e .              # from the repository root
pip install -e ".[examples]"  # plus the example scripts' dependencies
```

Python 3.10+, `llama-index-core` 0.14, and a MeetStream API key.

## The client

```python
from llama_index_meetstream import MeetStreamClient

client = MeetStreamClient(api_key="...")   # or set MEETSTREAM_API_KEY
```

`MeetStreamClient` calls MeetStream's REST API (`https://api.meetstream.ai/api/v1`, or
`MEETSTREAM_BASE_URL`). Share one instance between the reader and the tools to reuse its
connection pool.

### Transcription provider

```python
MeetStreamClient()                                            # MeetStream's own transcription (default)
MeetStreamClient(transcription_provider="deepgram",
                 transcription_options={"model": "nova-3", "language": "en"})
MeetStreamClient(transcription_provider=None)                 # bots record without a transcript

client.dispatch_bot(url, transcription_provider="assemblyai")  # per call
```

The provider applies to `dispatch_bot` and to the `dispatch_meetstream_bot` tool. Known
post-call providers are in `llama_index_meetstream.TRANSCRIPTION_PROVIDERS`. Some, such as
`smallest`, need an integration key saved in the MeetStream dashboard first.

## Loading transcripts: `MeetStreamReader`

```python
from llama_index_meetstream import MeetStreamReader

reader = MeetStreamReader(meeting_id="<bot id>", client=client)
documents = reader.load_data()       # list[Document]
for doc in reader.lazy_load_data():  # or lazily
    ...
```

The reader emits one `Document` (`text` plus `metadata`) per transcript segment (speaker
turn). Field details are in the [README](../README.md#transcript-metadata). An empty
transcript gives no documents. Items with no text are skipped. A missing speaker or time is
`None`. Errors are raised as `MeetStreamAPIError`; `transcript_not_ready` means try again later.

Async: `await reader.aload_data()` works through `BaseReader`'s default wrapping.

## Tools: `get_meetstream_tools`

```python
from llama_index_meetstream.tools import get_meetstream_tools

tools = get_meetstream_tools(client)   # list[FunctionTool], 6 tools
```

| Tool | Does |
|---|---|
| `dispatch_meetstream_bot` | Sends a bot to a meeting URL |
| `get_meeting` | The bot's current status |
| `get_meeting_transcript` | The transcript, as segments |
| `send_meeting_chat_message` | Posts in the meeting chat |
| `send_meeting_image` | Shows an image as the bot's video |
| `leave_meeting` | Makes the bot leave |

They're plain `FunctionTool`s, so they work with any LlamaIndex agent:

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI

agent = FunctionAgent(tools=tools, llm=OpenAI(model="gpt-4o-mini"))
response = await agent.run(user_msg="...")
```

Each is also importable on its own from `llama_index_meetstream.tools`.

## RAG

[`examples/rag_example.py`](../examples/rag_example.py):

```
MeetStream → MeetStreamReader → Documents → VectorStoreIndex → query engine
```

```bash
pip install -e ".[examples]"
python examples/rag_example.py <bot id> "What deadline was discussed?"
```

## Errors

```python
from llama_index_meetstream import MeetStreamAPIError

try:
    transcript = client.get_transcript("<bot id>")
except MeetStreamAPIError as exc:
    print(exc.code, exc.status_code, str(exc))
```

All codes are listed in [`exceptions.py`](../llama_index_meetstream/exceptions.py).
