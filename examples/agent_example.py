"""A LlamaIndex agent with MeetStream capabilities.

Demonstrates the "AI -> Meeting" direction: a user asks a normal LlamaIndex
`FunctionAgent` (the current recommended tool-calling agent) to do something
involving MeetStream, and the agent decides on its own which MeetStream tool
to call, e.g.:

    User: "Send a bot to https://meet.google.com/abc-defg-hij and tell me its meeting ID."
    Agent -> calls dispatch_meetstream_bot(meeting_url=..., bot_name=...)
    Agent -> replies with the bot_id from the tool's result

There is no special "MeetStream agent" class here -- `get_meetstream_tools`
just returns plain `FunctionTool` objects that work with any LlamaIndex agent.

Prerequisites:
    1. The bridge server running, pointed at a real MeetStream API key.
    2. `pip install -e ".[examples]"` from this package's directory.
    3. `OPENAI_API_KEY` set (swap `OpenAI` for any other LlamaIndex
       tool-calling LLM integration if you'd rather not use OpenAI).
    4. `MEETSTREAM_API_KEY` / `MEETSTREAM_BRIDGE_URL` set, or passed explicitly.

Run: `python examples/agent_example.py`
"""

from __future__ import annotations

import asyncio

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI

from llama_index_meetstream import MeetStreamClient
from llama_index_meetstream.tools import get_meetstream_tools


async def main() -> None:
    client = MeetStreamClient()  # reads MEETSTREAM_API_KEY / MEETSTREAM_BRIDGE_URL from the environment
    tools = get_meetstream_tools(client)

    agent = FunctionAgent(tools=tools, llm=OpenAI(model="gpt-4o-mini"))

    # 1. Dispatch a bot into a meeting.
    response = await agent.run(
        user_msg="Send a MeetStream bot to https://meet.google.com/abc-defg-hij and tell me its meeting ID."
    )
    print("Agent:", response)

    # 2. Retrieve a transcript. Transcription is asynchronous on MeetStream's
    # side (see docs/ARCHITECTURE.md §7) -- this example deliberately does
    # NOT poll in a loop waiting for it to finish. If you ask the agent to
    # fetch a transcript before MeetStream has finished processing it, the
    # get_meeting_transcript tool will raise a transcript_not_ready error,
    # which the agent will typically report back to you; ask again once the
    # meeting has ended and a short processing delay has passed.
    response = await agent.run(user_msg="What did people say in meeting meeting_123? Summarize the key points.")
    print("Agent:", response)


if __name__ == "__main__":
    asyncio.run(main())
