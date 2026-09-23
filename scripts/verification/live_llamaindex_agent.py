#!/usr/bin/env python3
"""REAL LlamaIndex agent end-to-end test: a real tool-calling LLM decides on
its own to call the `get_meeting_transcript` tool, against a real bridge and
a real, already-captured MeetStream transcript -- no mocks anywhere in the
loop.

This is the missing half of `live_llamaindex_tools.py`, which invokes tools
DIRECTLY with no LLM involved (proving the tool itself is correct). This
script instead proves the other half: given a normal user prompt and the
real tool set from `get_meetstream_tools`, does a real model actually choose
to call `get_meeting_transcript` with the right `meeting_id`, and produce a
sane final answer. See `examples/agent_example.py` for the demo-oriented
version of this same idea (not assertion-based).

Prerequisites:
    - A running bridge with a real MEETSTREAM_API_KEY (see live_llamaindex_test.py's docstring)
    - A --bot-id whose transcript is already processed (MeetStream-side)
    - OPENAI_API_KEY set, and `llama-index-llms-openai` installed
      (`pip install -e '.[examples]'`)

Usage:
    python scripts/verification/live_llamaindex_agent.py --bot-id <bot_id>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib

_LABEL_WIDTH = 43


def _line(label: str, status: str) -> str:
    return f"{label.ljust(_LABEL_WIDTH)}{status}"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bot-id", required=True, help="A real bot_id whose transcript is already processed")
    parser.add_argument("--bridge-url", default=_lib.DEFAULT_BRIDGE_URL)
    parser.add_argument("--model", default="gpt-4o-mini", help="Any llama-index-llms-openai OpenAI-compatible model name")
    args = parser.parse_args()

    print(f"Bridge URL: {args.bridge_url}")
    if not _lib.bridge_is_running(args.bridge_url):
        print(_line("Bridge connection", "FAIL") + f" (not reachable at {args.bridge_url})")
        print("next step: start it -- cd bridge && export MEETSTREAM_API_KEY=... && uvicorn app.main:app")
        return 1
    print(_line("Bridge connection", "PASS"))

    try:
        from llama_index.core.agent.workflow import FunctionAgent
        from llama_index.core.agent.workflow.workflow_events import ToolCallResult
        from llama_index.llms.openai import OpenAI
    except ImportError as exc:
        print(_line("llama-index-core/llama-index-llms-openai import", "FAIL") + f" ({exc})")
        print(f"next step: pip install -e '{_lib.LLAMAINDEX_DIR}[examples]'")
        return 1

    try:
        from llama_index_meetstream import MeetStreamClient
        from llama_index_meetstream.tools import get_meetstream_tools
    except ImportError as exc:
        print(_line("llama_index_meetstream import", "FAIL") + f" ({exc})")
        print(f"next step: pip install -e '{_lib.LLAMAINDEX_DIR}[dev]'")
        return 1

    if not os.environ.get("OPENAI_API_KEY"):
        print(_line("OPENAI_API_KEY", "FAIL") + " (not set)")
        print("next step: export OPENAI_API_KEY=... -- this script needs a real tool-calling model")
        return 1
    print(_line("OPENAI_API_KEY", "PASS") + " (set)")

    client = MeetStreamClient(api_key="live-verification", base_url=args.bridge_url)
    tools = get_meetstream_tools(client)
    tool_names = {t.metadata.name for t in tools}
    if "get_meeting_transcript" not in tool_names:
        print(_line("get_meeting_transcript tool present", "FAIL") + f" (tools: {sorted(tool_names)})")
        return 1
    print(_line("get_meeting_transcript tool present", "PASS"))

    agent = FunctionAgent(tools=tools, llm=OpenAI(model=args.model))

    prompt = f"What did people say in meeting {args.bot_id}? Give me a short summary."
    print(f"\nPrompt: {prompt!r}")

    handler = agent.run(user_msg=prompt)
    tool_call_results: list[ToolCallResult] = []
    async for event in handler.stream_events():
        if isinstance(event, ToolCallResult) and event.tool_name == "get_meeting_transcript":
            tool_call_results.append(event)
    response = await handler

    if not tool_call_results:
        print(_line("Agent called get_meeting_transcript", "FAIL") + " (model never invoked the tool)")
        print("next step: inspect the final response below -- the model may need a more explicit prompt")
        print(f"\nFinal response:\n{response}")
        return 1
    print(_line("Agent called get_meeting_transcript", "PASS") + f" ({len(tool_call_results)} call(s))")

    called_with_bot_id = any(call.tool_kwargs.get("meeting_id") == args.bot_id for call in tool_call_results)
    if not called_with_bot_id:
        print(
            _line("Agent passed the correct meeting_id", "FAIL")
            + f" (called with {[c.tool_kwargs for c in tool_call_results]})"
        )
        return 1
    print(_line("Agent passed the correct meeting_id", "PASS"))

    final_reply = str(response).strip()
    if not final_reply:
        print(_line("Agent produced a final reply", "FAIL") + " (empty)")
        return 1
    print(_line("Agent produced a final reply", "PASS"))

    print("\nFinal reply:")
    print(final_reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
