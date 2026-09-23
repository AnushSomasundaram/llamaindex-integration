#!/usr/bin/env python3
"""REAL LlamaIndex end-to-end test: a real bot's real, already-captured
transcript, loaded through the ACTUAL `MeetStreamReader` (no mocks).

Prerequisites: a running bridge with a real key, and a `--bot-id` whose
transcript is already ready (see `live_meetstream_test.py`).

Usage:
    python scripts/verification/live_llamaindex_test.py --bot-id <bot_id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bot-id", required=True, help="A real bot_id from live_meetstream_test.py dispatch")
    parser.add_argument("--bridge-url", default=_lib.DEFAULT_BRIDGE_URL)
    args = parser.parse_args()

    print(f"Bridge URL: {args.bridge_url}")
    if not _lib.bridge_is_running(args.bridge_url):
        print(f"Bridge connection                         FAIL (not reachable at {args.bridge_url})")
        print("next step: start it -- cd bridge && export MEETSTREAM_API_KEY=... && uvicorn app.main:app")
        return 1
    print("Bridge connection                         PASS")

    try:
        from llama_index_meetstream import MeetStreamAPIError, MeetStreamClient
        from llama_index_meetstream.readers import MeetStreamReader
    except ImportError as exc:
        print(f"LlamaIndex package import                  FAIL ({exc})")
        print(f"next step: pip install -e '{_lib.LLAMAINDEX_DIR}[dev]'")
        return 1

    client = MeetStreamClient(api_key="live-verification", base_url=args.bridge_url)

    try:
        transcript = client.get_transcript(args.bot_id)
    except MeetStreamAPIError as exc:
        if exc.code == "transcript_not_ready":
            print("Transcript fetched                        NOT READY (still processing)")
            return 2
        print(f"Transcript fetched                        FAIL ({exc.code}: {exc})")
        return 1
    print(f"Transcript fetched                        PASS ({len(transcript.segments)} real segment(s))")

    try:
        docs = MeetStreamReader(meeting_id=args.bot_id, client=client).load_data()
    except MeetStreamAPIError as exc:
        print(f"MeetStreamReader.load_data()               FAIL ({exc.code}: {exc})")
        return 1
    print("MeetStreamReader.load_data()               PASS")

    from llama_index.core.schema import Document

    if not all(isinstance(d, Document) for d in docs):
        print("Returned LlamaIndex Documents              FAIL (not all items are llama_index Document)")
        return 1
    print("Returned LlamaIndex Documents              PASS")
    print(f"Document count                             {len(docs)}")

    if not docs:
        print("(empty transcript -- a real meeting with zero captured segments is valid, not a bug)")
        return 0

    empty_content = [i for i, d in enumerate(docs) if not d.text or not d.text.strip()]
    if empty_content:
        print(f"Non-empty text                            FAIL (Document(s) at index {empty_content} have empty text)")
        return 1
    print("Non-empty text                            PASS")

    expected_keys = {"source", "meeting_id", "meeting_title", "platform", "speaker", "start_time", "end_time"}
    bad_metadata = [i for i, d in enumerate(docs) if set(d.metadata) != expected_keys]
    if bad_metadata:
        print(f"Metadata validation                       FAIL (Document(s) at index {bad_metadata} have unexpected metadata keys)")
        return 1
    print("Metadata validation                       PASS")

    print("\nSample Document(s):")
    for doc in docs[:2]:
        print(f"  text: {doc.text!r}")
        print(f"  metadata: {doc.metadata}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
