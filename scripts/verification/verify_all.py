#!/usr/bin/env python3
"""Master verification runner for the MeetStream LlamaIndex integration.

Runs every check that does NOT require manually joining a real meeting, and
prints one clear PASS/FAIL/SKIPPED/NOT RUN summary at the end. Never claims
something works unless the corresponding script actually verified it.

    python scripts/verification/verify_all.py                # local + packaging + live-availability (default)
    python scripts/verification/verify_all.py --local         # environment + bridge(static) + existing tests + ruff + llamaindex + git/security
    python scripts/verification/verify_all.py --packaging     # wheel builds + clean installs only
    python scripts/verification/verify_all.py --live          # + real-bridge availability check (never dispatches a bot)
    python scripts/verification/verify_all.py --live --bot-id <id>   # + real status/transcript check for an EXISTING bot (read-only, joins nothing)
    python scripts/verification/verify_all.py --start-bridge  # if no bridge is already running, spin up a throwaway one (placeholder key) for the static/structural bridge checks, then tear it down
    python scripts/verification/verify_all.py --report verification-report.md   # also write a markdown report

This script NEVER dispatches a real bot into a real meeting -- that is
always an explicit, separate action via `live_meetstream_test.py dispatch`.
See `scripts/verification/DEMO_CHECKLIST.md` for the full pre-demo sequence.
"""

from __future__ import annotations

import argparse
import datetime
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib
import check_bridge
import check_environment
import check_git_security
import check_llamaindex
import check_packaging
import check_tests


def _run_local(start_bridge: bool) -> list[_lib.CheckResult]:
    results = []
    results.extend(check_environment.run())
    results.extend(check_bridge.run(start_temporary=start_bridge))
    results.extend(check_tests.run())
    results.extend(check_llamaindex.run(verbose=False))
    results.extend(check_git_security.run())
    return results


def _run_live_section(bot_id: str | None, bridge_url: str) -> list[_lib.CheckResult]:
    """Live section is deliberately conservative: it NEVER dispatches a bot
    (that always requires the explicit `live_meetstream_test.py dispatch`
    command, run by you, against a meeting you chose). With `--bot-id` for an
    EXISTING bot, it will do a real, READ-ONLY status + transcript check
    (nothing here creates a new meeting join)."""
    import os

    results = []
    has_key = bool(os.environ.get("MEETSTREAM_API_KEY"))
    results.append(
        _lib.CheckResult(
            "MeetStream API key available",
            _lib.STATUS_PASS if has_key else _lib.STATUS_SKIP,
            hint="" if has_key else "export MEETSTREAM_API_KEY=... (your real key) before live verification",
        )
    )

    bridge_up = _lib.bridge_is_running(bridge_url)
    results.append(
        _lib.CheckResult(
            "Real bridge reachable",
            _lib.STATUS_PASS if bridge_up else _lib.STATUS_SKIP,
            detail=f"({bridge_url})",
            hint="" if bridge_up else "cd bridge && export MEETSTREAM_API_KEY=... && uvicorn app.main:app",
        )
    )

    if not bot_id:
        results.append(
            _lib.CheckResult(
                "Bot dispatch",
                _lib.STATUS_NOTRUN,
                hint="python scripts/verification/live_meetstream_test.py dispatch --meeting-url <your meeting url>",
            )
        )
        results.append(
            _lib.CheckResult(
                "Transcript retrieval",
                _lib.STATUS_NOTRUN,
                hint="python scripts/verification/live_meetstream_test.py transcript --bot-id <bot_id>",
            )
        )
        return results

    if not bridge_up:
        results.append(_lib.CheckResult("Bot status (real)", _lib.STATUS_SKIP, hint="bridge not reachable"))
        results.append(_lib.CheckResult("Transcript retrieval (real)", _lib.STATUS_SKIP, hint="bridge not reachable"))
        return results

    status, body = _lib.http_request_json("GET", f"{bridge_url}/meetings/{bot_id}", timeout=15)
    if status == 200:
        results.append(_lib.CheckResult("Bot status (real)", _lib.STATUS_PASS, detail=f"(status={body.get('status')})"))
    else:
        results.append(_lib.CheckResult("Bot status (real)", _lib.STATUS_FAIL, error=f"HTTP {status}: {body}"))

    t_status, t_body = _lib.http_request_json("GET", f"{bridge_url}/meetings/{bot_id}/transcript", timeout=30)
    if t_status == 200:
        results.append(_lib.CheckResult("Transcript retrieval (real)", _lib.STATUS_PASS, detail=f"({len(t_body.get('segments', []))} segments)"))
    elif t_status == 409:
        results.append(_lib.CheckResult("Transcript retrieval (real)", _lib.STATUS_SKIP, detail="(not ready yet)"))
    else:
        results.append(_lib.CheckResult("Transcript retrieval (real)", _lib.STATUS_FAIL, error=f"HTTP {t_status}: {t_body}"))

    return results


def _overall_line(label: str, results: list[_lib.CheckResult]) -> str:
    """PASSED only if every single check actually passed. FAILED if any
    check genuinely failed (takes priority). Otherwise -- no failures, but
    at least one SKIPPED/NOT RUN check (e.g. no API key, or a live dispatch
    you haven't run yet) -- NOT YET COMPLETED, since something real hasn't
    actually been confirmed working. Never says PASSED for something that
    was only partially checked."""
    if not results:
        return f"{label}: NOT RUN"
    if any(r.status == _lib.STATUS_FAIL for r in results):
        return f"{label}: FAILED"
    if any(r.status in (_lib.STATUS_SKIP, _lib.STATUS_NOTRUN) for r in results):
        return f"{label}: NOT YET COMPLETED"
    return f"{label}: PASSED"


def _write_report(path: Path, sections: dict[str, list[_lib.CheckResult]]) -> None:
    lines = ["# MeetStream Integration Verification Report", ""]
    # `.astimezone()` attaches the local zone offset (rather than a naive
    # timestamp) without forcing this report into UTC -- local time is what's
    # actually useful when checking "was this run right before the demo?"
    lines.append(f"- Generated: {datetime.datetime.now().astimezone().isoformat(timespec='seconds')}")
    lines.append(f"- Python: {platform.python_version()} ({platform.system()} {platform.release()})")

    code, out, _ = _lib.git(["rev-parse", "--short", "HEAD"])
    lines.append(f"- Git commit: {out.strip() if code == 0 else 'unknown (no commits yet?)'}")
    lines.append("")
    lines.append(
        "> **VERIFIED AGAINST MOCKS** below means: real project code (loaders, readers, tools, "
        "bridge routes) was exercised, but all HTTP responses were mocked with `respx` -- no "
        "network call to a real bridge or real MeetStream occurred.\n>\n"
        "> **VERIFIED AGAINST REAL MEETSTREAM API** means: an actual HTTP call reached a running "
        "bridge process, which made an actual call to MeetStream's real API."
    )

    for title, results in sections.items():
        lines.append(f"\n## {title}\n")
        if not results:
            lines.append("_Not run this invocation._")
            continue
        for r in results:
            lines.append(f"- **{r.name}**: {r.status}{f' — {r.detail}' if r.detail else ''}{f' (error: {r.error})' if r.error else ''}")

    lines.append("\n## Known limitations\n")
    lines.append("- See `docs/ARCHITECTURE.md` for the full, current list (bridge auth not yet enforced, no webhook ingestion, meeting_title/timestamps unavailable from MeetStream's API, transcript file schema defensively parsed).")

    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--local", action="store_true", help="Run only: environment, bridge (static), existing tests+ruff, LlamaIndex, git/security")
    parser.add_argument("--packaging", action="store_true", help="Run only: wheel builds + clean-venv installs")
    parser.add_argument("--live", action="store_true", help="Run only: real MeetStream API availability/status section (never dispatches a bot)")
    parser.add_argument("--start-bridge", action="store_true", help="If no bridge is running, start a temporary one (placeholder key) for the STATIC bridge checks only")
    parser.add_argument("--bot-id", default=None, help="An EXISTING real bot_id to check status/transcript for, in --live mode (read-only)")
    parser.add_argument("--bridge-url", default=_lib.DEFAULT_BRIDGE_URL)
    parser.add_argument("--report", metavar="PATH", nargs="?", const="verification-report.md", default=None, help="Write a markdown report (default path: verification-report.md)")
    args = parser.parse_args()

    # No flags at all = run everything that doesn't require a real meeting:
    # local + packaging, plus the (non-dispatching) live-availability section.
    run_local = args.local or not (args.local or args.packaging or args.live)
    run_packaging = args.packaging or not (args.local or args.packaging or args.live)
    run_live = args.live or not (args.local or args.packaging or args.live)

    print("=" * 40)
    print("MeetStream Integration Verification")
    print("=" * 40)

    sections: dict[str, list[_lib.CheckResult]] = {}

    if run_local:
        _lib.print_section("LOCAL / MOCKED VERIFICATION")
        local_results = _run_local(start_bridge=args.start_bridge)
        for r in local_results:
            _lib.print_result(r)
        sections["Local / mocked verification"] = local_results
    else:
        local_results = []

    if run_packaging:
        _lib.print_section("PACKAGING VERIFICATION")
        packaging_results = check_packaging.run()
        for r in packaging_results:
            _lib.print_result(r)
        sections["Packaging verification"] = packaging_results
    else:
        packaging_results = []

    if run_live:
        _lib.print_section("REAL MEETSTREAM API")
        live_results = _run_live_section(args.bot_id, args.bridge_url)
        for r in live_results:
            _lib.print_result(r)
        sections["Real MeetStream API"] = live_results
    else:
        live_results = []

    print("\n" + "=" * 40)
    print("Overall:")
    if run_local:
        print(_overall_line("LOCAL VERIFICATION", local_results))
    if run_packaging:
        print(_overall_line("PACKAGING VERIFICATION", packaging_results))
    if run_live:
        print(_overall_line("LIVE VERIFICATION", live_results))
    print("=" * 40)

    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = _lib.REPO_ROOT / report_path
        _write_report(report_path, sections)
        print(f"\nReport written to {report_path}")

    all_results = local_results + packaging_results + live_results
    return 0 if all(r.status != _lib.STATUS_FAIL for r in all_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
