#!/usr/bin/env python3
"""Invoke MeetStream LlamaIndex tools DIRECTLY, against a REAL bridge/real
MeetStream, with no LLM in the loop. This is the complement to
`live_llamaindex_agent.py`, which proves an LLM's *decision* to call a tool
-- this script proves the tool itself is correct, independent of any model.

Reads each tool's REAL input schema (`FunctionTool.metadata.fn_schema`)
rather than a hardcoded parameter list.

Usage:
    python scripts/verification/live_llamaindex_tools.py list
    python scripts/verification/live_llamaindex_tools.py invoke get_meeting --json '{"meeting_id": "abc123"}'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib


def _load_tools(bridge_url: str):
    from llama_index_meetstream import MeetStreamClient
    from llama_index_meetstream.tools import get_meetstream_tools

    client = MeetStreamClient(api_key="live-verification", base_url=bridge_url)
    return {t.metadata.name: t for t in get_meetstream_tools(client)}


def cmd_list(args: argparse.Namespace) -> int:
    tools = _load_tools(args.bridge_url)
    for name, tool in sorted(tools.items()):
        print(f"Tool: {name}")
        desc_lines = (tool.metadata.description or "").splitlines()
        summary = desc_lines[1] if len(desc_lines) > 1 else (desc_lines[0] if desc_lines else "(no description)")
        print(f"  Description: {summary}")
        schema = tool.metadata.fn_schema.model_json_schema() if tool.metadata.fn_schema else {}
        required = set(schema.get("required", []))
        for field_name, field_info in schema.get("properties", {}).items():
            marker = "required" if field_name in required else f"optional, default={field_info.get('default')!r}"
            print(f"  Param: {field_name} ({field_info.get('type', 'unknown')}, {marker})")
        print()
    return 0


def cmd_invoke(args: argparse.Namespace) -> int:
    tools = _load_tools(args.bridge_url)
    if args.tool_name not in tools:
        print(f"FAIL: no such tool {args.tool_name!r}. Known tools: {sorted(tools)}")
        return 1

    try:
        kwargs = json.loads(args.json)
    except json.JSONDecodeError as exc:
        print(f"FAIL: --json is not valid JSON: {exc}")
        return 1

    tool = tools[args.tool_name]
    print(f"Invoking {args.tool_name} with {kwargs}")
    from llama_index_meetstream import MeetStreamAPIError, MeetStreamConnectionError

    try:
        result = tool.call(**kwargs)
    except MeetStreamConnectionError as exc:
        print(f"FAIL: could not reach bridge ({exc})")
        return 1
    except MeetStreamAPIError as exc:
        print(f"FAIL: bridge/MeetStream returned an error -- code={exc.code}: {exc}")
        return 1

    print("PASS")
    print(json.dumps(result.raw_output, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bridge-url", default=_lib.DEFAULT_BRIDGE_URL)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List every tool with its real schema")
    p_list.set_defaults(func=cmd_list)

    p_invoke = sub.add_parser("invoke", help="Invoke one tool directly")
    p_invoke.add_argument("tool_name")
    p_invoke.add_argument("--json", required=True, help='JSON object of arguments, e.g. \'{"meeting_id": "abc123"}\'')
    p_invoke.set_defaults(func=cmd_invoke)

    args = parser.parse_args()
    print(f"Bridge URL: {args.bridge_url}")
    if not _lib.bridge_is_running(args.bridge_url):
        print(f"FAIL: bridge not reachable at {args.bridge_url}/health")
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
