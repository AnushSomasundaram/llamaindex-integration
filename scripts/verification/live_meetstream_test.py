#!/usr/bin/env python3
"""REAL MeetStream verification, through the REAL bridge -- no mocks.

This script NEVER runs as part of `verify_all.py`'s default invocation. You
must run it explicitly, and it never starts a bridge for you -- it only
talks to a bridge you already have running (see docs/BRIDGE_SERVER.md /
docs/DEVELOPMENT.md for how to start one against your real MeetStream key).

Deliberately talks to the bridge with plain HTTP (see
`_lib.http_request_json`), not through `llama_index_meetstream` -- this
script verifies the bridge + real MeetStream, a layer below the framework
package. See `live_llamaindex_test.py` for the framework-level real-data
checks, which build on a bot_id this script produces.

Subcommands:

    # 1. Dispatch a real bot into a real meeting you control and are alone in.
    python scripts/verification/live_meetstream_test.py dispatch \\
        --meeting-url "https://meet.google.com/xxx-xxxx-xxx"

    # 2. Check on it (repeatable -- watch it progress joining -> in meeting).
    python scripts/verification/live_meetstream_test.py status --bot-id <bot_id>

    # 3. Make it leave.
    python scripts/verification/live_meetstream_test.py leave --bot-id <bot_id>

    # 4. Fetch the real transcript once MeetStream has processed it.
    python scripts/verification/live_meetstream_test.py transcript --bot-id <bot_id>

Never prints your API key (the bridge holds it server-side; this script
never even sees it -- see docs/ARCHITECTURE.md §8a for what a client-side
`api_key` would mean here, which this bridge-focused script doesn't use at
all).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib


def _require_bridge(base_url: str) -> None:
    if not _lib.bridge_is_running(base_url):
        print(f"FAIL: no bridge reachable at {base_url}/health")
        print("next step: start it against a REAL MeetStream key -- cd bridge && export MEETSTREAM_API_KEY=... && uvicorn app.main:app")
        raise SystemExit(1)


def cmd_dispatch(args: argparse.Namespace) -> int:
    base_url = args.bridge_url
    print(f"Bridge URL: {base_url}")
    _require_bridge(base_url)
    print("Bridge reachable                    PASS")

    status, body = _lib.http_request_json(
        "POST", f"{base_url}/bots", {"meeting_url": args.meeting_url, "bot_name": args.bot_name}, timeout=30
    )
    if status != 200:
        print("Request sent through bridge          PASS")
        print(f"MeetStream accepted request           FAIL (HTTP {status})")
        print(f"error: {body}")
        return 1

    print("Request sent through bridge          PASS")
    print("MeetStream accepted request          PASS")
    print(f"bot_id                               {body['bot_id']}")
    print(f"Bot state                            {body['status']}")
    print()
    print("Go check the meeting -- you should see the bot join shortly.")
    print(f"Follow up with:\n  python {Path(__file__).name} status --bot-id {body['bot_id']} --bridge-url {base_url}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    base_url = args.bridge_url
    print(f"Bridge URL: {base_url}")
    _require_bridge(base_url)

    status, body = _lib.http_request_json("GET", f"{base_url}/meetings/{args.bot_id}", timeout=15)
    if status != 200:
        print(f"Meeting lookup                       FAIL (HTTP {status})")
        print(f"error: {body}")
        return 1

    print("Meeting lookup                       PASS")
    for key in ("meeting_id", "status", "platform", "meeting_url", "title", "started_at", "ended_at"):
        print(f"  {key:<14} {body.get(key)}")
    return 0


def cmd_leave(args: argparse.Namespace) -> int:
    base_url = args.bridge_url
    print(f"Bridge URL: {base_url}")
    _require_bridge(base_url)

    status, body = _lib.http_request_json(
        "POST", f"{base_url}/meetings/{args.bot_id}/actions", {"action": "leave_meeting"}, timeout=30
    )
    if status != 200:
        print(f"Leave-meeting action                 FAIL (HTTP {status})")
        print(f"error: {body}")
        return 1

    print("Leave-meeting action                 PASS")
    print(f"  detail: {body.get('detail')}")
    return 0


def cmd_transcript(args: argparse.Namespace) -> int:
    base_url = args.bridge_url
    print(f"Bridge URL: {base_url}")
    _require_bridge(base_url)

    status, body = _lib.http_request_json("GET", f"{base_url}/meetings/{args.bot_id}/transcript", timeout=30)
    if status == 409:
        print("Transcript retrieval                 NOT READY (still processing)")
        print(f"  {body.get('error', {}).get('message')}")
        print("Try again in a bit -- this is expected right after a meeting ends.")
        return 2
    if status != 200:
        print(f"Transcript retrieval                 FAIL (HTTP {status})")
        print(f"error: {body}")
        if status == 502 and body.get("error", {}).get("code") == "transcript_format_error":
            print("This is the exact failure mode docs/ARCHITECTURE.md §3/§7 warned about --")
            print("MeetStream's downloaded transcript file didn't match any recognized shape.")
            print("Raw error above should have enough structural detail to debug the parser.")
        return 1

    print("Transcript retrieval                 PASS")
    segments = body.get("segments", [])
    print(f"Segment count                         {len(segments)}")
    if not segments:
        print("(empty transcript -- a real meeting with zero captured segments is valid, not a bug)")
        return 0

    fabrication_problems = [s for s in segments if not isinstance(s.get("text"), str) or not s["text"].strip()]
    if fabrication_problems:
        print(f"FAIL: {len(fabrication_problems)} segment(s) have no real text")
        return 1

    print("\nFirst 3 segments (safe preview):")
    for i, seg in enumerate(segments[:3], start=1):
        speaker = seg.get("speaker") or "(speaker not identified)"
        start = seg.get("start_time")
        end = seg.get("end_time")
        print(f"  [{i}] {speaker} @ {start}-{end}s: {seg['text']!r}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bridge-url", default=_lib.DEFAULT_BRIDGE_URL, help=f"default: {_lib.DEFAULT_BRIDGE_URL}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_dispatch = sub.add_parser("dispatch", help="Send a real bot into a real meeting")
    p_dispatch.add_argument("--meeting-url", required=True)
    p_dispatch.add_argument("--bot-name", default="MeetStream Verification Bot")
    p_dispatch.set_defaults(func=cmd_dispatch)

    p_status = sub.add_parser("status", help="Look up a bot/meeting's current status")
    p_status.add_argument("--bot-id", required=True)
    p_status.set_defaults(func=cmd_status)

    p_leave = sub.add_parser("leave", help="Make the bot leave its meeting")
    p_leave.add_argument("--bot-id", required=True)
    p_leave.set_defaults(func=cmd_leave)

    p_transcript = sub.add_parser("transcript", help="Fetch the real, processed transcript")
    p_transcript.add_argument("--bot-id", required=True)
    p_transcript.set_defaults(func=cmd_transcript)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
