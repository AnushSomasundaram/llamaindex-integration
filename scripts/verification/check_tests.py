#!/usr/bin/env python3
"""Runs this repository's TWO existing, already-written test suites
(`bridge/tests`, `tests/`) plus each project's Ruff lint config, exactly as
documented in `docs/DEVELOPMENT.md` -- and reports the REAL pass/fail counts
pytest itself reports, never a hardcoded number.

These are all MOCKED tests -- every one of them mocks HTTP with `respx` (see
each project's own `tests/conftest.py`); none of them talk to a real bridge
or real MeetStream. That's deliberate and is exactly what this script is
verifying still holds -- it is a different category from
`check_bridge.py`'s real `/health` check or `live_meetstream_test.py`'s real
MeetStream calls.

Standalone usage:
    python scripts/verification/check_tests.py

Importable:
    from check_tests import run
    results = run()
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib

_PROJECTS = [
    (_lib.BRIDGE_DIR, ["app", "tests"]),
    (_lib.LLAMAINDEX_DIR, ["llama_index_meetstream", "tests", "examples"]),
]


def run() -> list[_lib.CheckResult]:
    results = []
    for project_dir, ruff_targets in _PROJECTS:
        if not project_dir.exists():
            results.append(_lib.CheckResult(f"{project_dir.name} tests", _lib.STATUS_FAIL, error=f"{project_dir} does not exist"))
            continue
        test_result, _ = _lib.run_pytest(project_dir)
        results.append(test_result)
        lint_result, _ = _lib.run_ruff(project_dir, ruff_targets)
        results.append(lint_result)
    return results


def main() -> int:
    _lib.print_section("Mocked automated test suites (existing repository tests)")
    results = run()
    for r in results:
        _lib.print_result(r)
    total_tests = sum(int(r.detail.strip("()").split()[0]) for r in results if r.status == _lib.STATUS_PASS and "tests)" in r.detail)
    print(f"\nTotal tests passed across both projects: {total_tests}")
    return 0 if all(r.status != _lib.STATUS_FAIL for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
