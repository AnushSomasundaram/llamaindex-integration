"""Basic MeetStreamReader usage.

Prerequisites:
    1. The bridge server running (see ../../bridge/README.md), pointed at a
       real MeetStream API key.
    2. A meeting_id for a MeetStream meeting whose transcript has already
       finished processing.
    3. `MEETSTREAM_API_KEY` and `MEETSTREAM_BRIDGE_URL` set in the
       environment, or passed explicitly below.

Run: `python examples/reader_example.py <meeting_id>`
"""

from __future__ import annotations

import sys

from llama_index_meetstream import MeetStreamAPIError, MeetStreamReader


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <meeting_id>")
        raise SystemExit(1)
    meeting_id = sys.argv[1]

    # api_key/base_url default to the MEETSTREAM_API_KEY / MEETSTREAM_BRIDGE_URL
    # environment variables if not passed explicitly -- see the package README.
    reader = MeetStreamReader(meeting_id=meeting_id)

    try:
        documents = reader.load_data()
    except MeetStreamAPIError as exc:
        if exc.code == "transcript_not_ready":
            print("Transcript is still processing -- try again in a bit.")
            return
        raise

    if not documents:
        print(f"No transcript segments found for meeting {meeting_id} (empty transcript).")
        return

    for doc in documents:
        print(f"[{doc.metadata['speaker'] or 'Unknown'} @ {doc.metadata['start_time']}s] {doc.text}")
        print(f"  metadata: {doc.metadata}")


if __name__ == "__main__":
    main()
