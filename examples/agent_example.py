"""A LlamaIndex agent with MeetStream capabilities.

Demonstrates the "AI -> Meeting" direction: a user asks a normal LlamaIndex
`FunctionAgent` (the current recommended tool-calling agent) to do something
involving MeetStream, and the agent decides on its own which MeetStream tool
to call, e.g.:

    User: "Send a bot to <meeting url> and tell me its meeting ID."
    Agent -> calls dispatch_meetstream_bot(meeting_url=..., bot_name=...)
    Agent -> replies with the bot_id from the tool's result

There is no special "MeetStream agent" class here -- `get_meetstream_tools`
just returns plain `FunctionTool` objects that work with any LlamaIndex agent.

Prerequisites:
    1. `pip install -e ".[examples]"` from the repository root.
    2. `MEETSTREAM_API_KEY` set.
    3. `OPENAI_API_KEY` set (or swap `OpenAI` for any other LlamaIndex
       tool-calling LLM integration).

Run: `python examples/agent_example.py <meeting url> [<bot id with a finished transcript>]`
"""

from __future__ import annotations

import asyncio
import sys

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI

from llama_index_meetstream import MeetStreamClient
from llama_index_meetstream.tools import get_meetstream_tools


async def main() -> None:
    if len(sys.argv) not in (2, 3):
        print(f"Usage: python {sys.argv[0]} <meeting url> [<bot id with a finished transcript>]")
        raise SystemExit(1)
    meeting_url = sys.argv[1]
    finished_bot_id = sys.argv[2] if len(sys.argv) == 3 else None

    client = MeetStreamClient()  # reads MEETSTREAM_API_KEY; bots use MeetStream's own transcription
    tools = get_meetstream_tools(client)

    agent = FunctionAgent(tools=tools, llm=OpenAI(model="gpt-4o-mini"))

    # 1. Dispatch a bot into a meeting.
    response = await agent.run(
        user_msg=f"Send a MeetStream bot to {meeting_url} and tell me its meeting ID."
    )
    print("Agent:", response)

    # 2. Retrieve a transcript. Transcription is asynchronous on MeetStream's
    # side -- this example deliberately does
    # NOT poll in a loop waiting for it to finish. If you ask the agent to
    # fetch a transcript before MeetStream has finished processing it, the
    # get_meeting_transcript tool will raise a transcript_not_ready error,
    # which the agent will typically report back to you; ask again once the
    # meeting has ended and a short processing delay has passed.
    if finished_bot_id:
        response = await agent.run(user_msg=f"What did people say in meeting {finished_bot_id}? Summarize the key points.")
        print("Agent:", response)


if __name__ == "__main__":
    asyncio.run(main())
