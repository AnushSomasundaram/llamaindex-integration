#!/usr/bin/env python3
"""LlamaIndex package smoke test -- MOCKED bridge responses only (no real
bridge or MeetStream call). For a real-data version, see
`live_llamaindex_test.py`, which requires a real `--bot-id`.

Ground rules: exercises real project code, mocks HTTP only, never fabricates
a field.

Standalone usage:
    python scripts/verification/check_llamaindex.py

Importable:
    from check_llamaindex import run
    results = run()
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib

_MOCK_BRIDGE_URL = "http://verification-mock-bridge"


def check_imports() -> _lib.CheckResult:
    try:
        from llama_index_meetstream import (  # noqa: F401
            MeetStreamAPIError,
            MeetStreamClient,
            MeetStreamConnectionError,
            MeetStreamReader,
        )
        from llama_index_meetstream.tools import get_meetstream_tools  # noqa: F401
    except ImportError as exc:
        return _lib.CheckResult(
            "LlamaIndex package imports",
            _lib.STATUS_FAIL,
            error=str(exc),
            hint=f"pip install -e '{_lib.LLAMAINDEX_DIR}[dev]'",
        )
    return _lib.CheckResult("LlamaIndex package imports", _lib.STATUS_PASS)


def check_client_construction() -> _lib.CheckResult:
    try:
        from llama_index_meetstream import MeetStreamClient

        client = MeetStreamClient(api_key="verification-mock-key", base_url=_MOCK_BRIDGE_URL)
        client.close()
    except Exception as exc:  # noqa: BLE001 -- catches any failure from the real project code under test, not just anticipated ones
        return _lib.CheckResult("LlamaIndex client construction", _lib.STATUS_FAIL, error=str(exc))
    return _lib.CheckResult("LlamaIndex client construction", _lib.STATUS_PASS)


def check_reader() -> list[_lib.CheckResult]:
    import httpx
    import respx

    from llama_index_meetstream import MeetStreamClient
    from llama_index_meetstream.readers import MeetStreamReader

    results = []
    try:
        with respx.mock(base_url=_MOCK_BRIDGE_URL, assert_all_called=False) as router:
            router.get("/meetings/verify-meeting-1/transcript").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "meeting_id": "verify-meeting-1",
                        "segments": [
                            {"text": "The launch date is October 14.", "speaker": "Sarah", "start_time": 1.0, "end_time": 4.5},
                            {"text": "Understood, thanks."},
                        ],
                    },
                )
            )
            router.get("/meetings/verify-meeting-1").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "meeting_id": "verify-meeting-1",
                        "status": "completed",
                        "platform": None,
                        "meeting_url": None,
                        "title": None,
                        "started_at": None,
                        "ended_at": None,
                        "custom_attributes": None,
                    },
                )
            )
            client = MeetStreamClient(api_key="verification-mock-key", base_url=_MOCK_BRIDGE_URL)
            docs = MeetStreamReader(meeting_id="verify-meeting-1", client=client).load_data()
    except Exception as exc:  # noqa: BLE001 -- catches any failure from the real project code under test, not just anticipated ones
        return [_lib.CheckResult("LlamaIndex reader (mocked)", _lib.STATUS_FAIL, error=str(exc))]

    from llama_index.core.schema import Document

    if len(docs) != 2 or not all(isinstance(d, Document) for d in docs):
        return [_lib.CheckResult("LlamaIndex reader returns Documents", _lib.STATUS_FAIL, error=f"expected 2 llama_index Document objects, got {docs!r}")]
    results.append(_lib.CheckResult("LlamaIndex reader returns Documents", _lib.STATUS_PASS, detail=f"({len(docs)} Documents)"))

    if docs[0].text != "The launch date is October 14.":
        results.append(_lib.CheckResult("LlamaIndex reader text", _lib.STATUS_FAIL, error=f"unexpected text: {docs[0].text!r}"))
    else:
        results.append(_lib.CheckResult("LlamaIndex reader text", _lib.STATUS_PASS))

    md = docs[0].metadata
    expected_keys = {"source", "meeting_id", "meeting_title", "platform", "speaker", "start_time", "end_time"}
    if set(md) != expected_keys or md["speaker"] != "Sarah" or md["start_time"] != 1.0:
        results.append(_lib.CheckResult("LlamaIndex reader metadata", _lib.STATUS_FAIL, error=f"unexpected metadata: {md}"))
    else:
        results.append(_lib.CheckResult("LlamaIndex reader metadata", _lib.STATUS_PASS))

    md2 = docs[1].metadata
    no_fabrication_ok = md2["speaker"] is None and md2["start_time"] is None and md2["end_time"] is None and md2["meeting_title"] is None
    if not no_fabrication_ok:
        results.append(
            _lib.CheckResult(
                "LlamaIndex reader does not fabricate missing fields",
                _lib.STATUS_FAIL,
                error=f"expected speaker/start_time/end_time/meeting_title to be None for an incomplete segment, got: {md2}",
            )
        )
    else:
        results.append(_lib.CheckResult("LlamaIndex reader does not fabricate missing fields", _lib.STATUS_PASS))

    return results


def check_tools(verbose: bool = True) -> list[_lib.CheckResult]:
    from llama_index_meetstream import MeetStreamClient
    from llama_index_meetstream.tools import get_meetstream_tools

    expected_tool_names = {
        "dispatch_meetstream_bot",
        "get_meeting",
        "get_meeting_transcript",
        "send_meeting_chat_message",
        "send_meeting_image",
        "leave_meeting",
    }

    client = MeetStreamClient(api_key="verification-mock-key", base_url=_MOCK_BRIDGE_URL)
    tools = get_meetstream_tools(client)
    results = []

    actual_names = {t.metadata.name for t in tools}
    if actual_names != expected_tool_names:
        results.append(
            _lib.CheckResult(
                "LlamaIndex tools discovered",
                _lib.STATUS_FAIL,
                error=f"expected {sorted(expected_tool_names)}, got {sorted(actual_names)}",
            )
        )
    else:
        results.append(_lib.CheckResult("LlamaIndex tools discovered", _lib.STATUS_PASS, detail=f"({len(tools)} tools)"))

    if verbose:
        print()
        for i, tool in enumerate(tools, start=1):
            print(f"Tool {i}: {tool.metadata.name}")
            # FunctionTool's auto-generated description is
            # "<name><signature>\n<docstring>" (see
            # llama_index.core.tools.FunctionTool.from_defaults) -- the first
            # docstring line (index 1, after the signature line at index 0)
            # is the one-line human summary; later lines are the full Args
            # block, not useful as a one-line preview here.
            lines = (tool.metadata.description or "").splitlines()
            summary = lines[1] if len(lines) > 1 else (lines[0] if lines else "(none)")
            print(f"Description: {summary}")
        print()

    for tool in tools:
        label = f"  {tool.metadata.name}"
        problems = []
        if not tool.metadata.name:
            problems.append("empty name")
        if not tool.metadata.description or len(tool.metadata.description.strip()) < 20:
            problems.append("description missing or too short to be useful")
        if tool.metadata.fn_schema is None:
            problems.append("no fn_schema (input schema)")
        if problems:
            results.append(_lib.CheckResult(f"{label} well-formed", _lib.STATUS_FAIL, error="; ".join(problems)))
        else:
            results.append(_lib.CheckResult(f"{label} well-formed", _lib.STATUS_PASS))

    return results


def check_tool_invocation() -> list[_lib.CheckResult]:
    import httpx
    import respx

    from llama_index_meetstream import MeetStreamClient
    from llama_index_meetstream.tools import get_meetstream_tools

    results = []
    with respx.mock(base_url=_MOCK_BRIDGE_URL, assert_all_called=False) as router:
        router.post("/bots").mock(return_value=httpx.Response(200, json={"bot_id": "b1", "meeting_id": "b1", "status": "Active"}))
        router.get("/meetings/b1").mock(return_value=httpx.Response(200, json={"meeting_id": "b1", "status": "InMeeting"}))
        router.get("/meetings/b1/transcript").mock(return_value=httpx.Response(200, json={"meeting_id": "b1", "segments": []}))
        router.post("/meetings/b1/actions").mock(
            return_value=httpx.Response(200, json={"meeting_id": "b1", "action": "send_chat_message", "status": "ok", "detail": "sent"})
        )

        client = MeetStreamClient(api_key="verification-mock-key", base_url=_MOCK_BRIDGE_URL)
        tools = {t.metadata.name: t for t in get_meetstream_tools(client)}

        invocations = [
            ("dispatch_meetstream_bot", {"meeting_url": "https://meet.google.com/verify-abc", "bot_name": "Verify Bot"}),
            ("get_meeting", {"meeting_id": "b1"}),
            ("get_meeting_transcript", {"meeting_id": "b1"}),
            ("send_meeting_chat_message", {"meeting_id": "b1", "message": "verification message"}),
        ]
        for name, kwargs in invocations:
            try:
                output = tools[name].call(**kwargs)
                results.append(_lib.CheckResult(f"  invoke {name}", _lib.STATUS_PASS, detail=f"-> {output.raw_output}"[:100]))
            except Exception as exc:  # noqa: BLE001 -- catches any failure from the real project code under test, not just anticipated ones
                results.append(_lib.CheckResult(f"  invoke {name}", _lib.STATUS_FAIL, error=str(exc)))
    return results


def run(verbose: bool = True) -> list[_lib.CheckResult]:
    results = [check_imports()]
    if results[0].status == _lib.STATUS_FAIL:
        return results
    results.append(check_client_construction())
    results.extend(check_reader())
    results.extend(check_tools(verbose=verbose))
    results.extend(check_tool_invocation())
    return results


def main() -> int:
    _lib.print_section("LlamaIndex package verification (mocked bridge)")
    results = run(verbose=True)
    for r in results:
        _lib.print_result(r)
    return 0 if all(r.status != _lib.STATUS_FAIL for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
