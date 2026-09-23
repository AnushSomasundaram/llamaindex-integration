#!/usr/bin/env python3
"""Environment / configuration verification.

Checks that the variables this project actually reads (see
`bridge/app/config.py` and `llama_index_meetstream`'s `client.py`) are set,
without ever printing their values. Also sanity-checks
`.env.example` for the variable names this project documents, and flags if
something that looks like a real secret has been pasted into it (which
should only ever contain empty placeholders).

Standalone usage:
    python scripts/verification/check_environment.py

Importable:
    from check_environment import run
    results = run()
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib

# The exact variable names this project's own code reads -- see
# bridge/app/config.py (env_prefix="") and llama_index_meetstream/client.py.
REQUIRED_FOR_BRIDGE = ["MEETSTREAM_API_KEY"]
OPTIONAL_FOR_BRIDGE = ["MEETSTREAM_BASE_URL"]
REQUIRED_FOR_CLIENTS = ["MEETSTREAM_API_KEY"]  # same var name, sent to the bridge instead -- see docs/ARCHITECTURE.md §8a
OPTIONAL_FOR_CLIENTS = ["MEETSTREAM_BRIDGE_URL"]

# A crude but useful check: .env.example should only ever contain
# `NAME=` or `NAME=<placeholder text>` -- never a value that looks like a
# real MeetStream key (MeetStream keys observed in this project start with
# "ms_") or a long opaque token.
_SUSPICIOUS_VALUE_RE = re.compile(r"^(ms_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9]{10,})$")


def _mask_status(var_name: str) -> _lib.CheckResult:
    value = os.environ.get(var_name)
    if value:
        return _lib.CheckResult(var_name, _lib.STATUS_PASS, detail="SET")
    return _lib.CheckResult(
        var_name,
        _lib.STATUS_SKIP,
        detail="NOT SET",
        hint=f"export {var_name}=... or add it to bridge/.env / your shell env",
    )


def check_required_vars() -> list[_lib.CheckResult]:
    results = []
    for var in dict.fromkeys(REQUIRED_FOR_BRIDGE + REQUIRED_FOR_CLIENTS):  # de-dup, preserve order
        results.append(_mask_status(var))
    return results


def check_bridge_url() -> _lib.CheckResult:
    url = os.environ.get("MEETSTREAM_BRIDGE_URL") or _lib.DEFAULT_BRIDGE_URL
    source = "MEETSTREAM_BRIDGE_URL" if os.environ.get("MEETSTREAM_BRIDGE_URL") else "default"
    return _lib.CheckResult("MEETSTREAM_BRIDGE_URL", _lib.STATUS_PASS, detail=f"{url} ({source})")


def check_env_example() -> _lib.CheckResult:
    path = _lib.REPO_ROOT / ".env.example"
    if not path.exists():
        return _lib.CheckResult(".env.example exists", _lib.STATUS_FAIL, error=f"{path} not found")

    text = path.read_text()
    missing = [
        var
        for var in dict.fromkeys(REQUIRED_FOR_BRIDGE + OPTIONAL_FOR_BRIDGE + REQUIRED_FOR_CLIENTS + OPTIONAL_FOR_CLIENTS)
        if not re.search(rf"^{re.escape(var)}=", text, re.MULTILINE)
    ]
    if missing:
        return _lib.CheckResult(
            ".env.example completeness",
            _lib.STATUS_FAIL,
            error=f"missing variable(s): {', '.join(missing)}",
            hint="add the missing variable name(s) to .env.example",
        )
    return _lib.CheckResult(".env.example completeness", _lib.STATUS_PASS, detail=f"({len(set(REQUIRED_FOR_BRIDGE + OPTIONAL_FOR_BRIDGE + REQUIRED_FOR_CLIENTS + OPTIONAL_FOR_CLIENTS))} vars documented)")


def check_env_example_no_real_secrets() -> _lib.CheckResult:
    path = _lib.REPO_ROOT / ".env.example"
    if not path.exists():
        return _lib.CheckResult(".env.example secret scan", _lib.STATUS_SKIP, hint=".env.example not found")

    offenders = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if "=" not in line or line.strip().startswith("#"):
            continue
        _, _, value = line.partition("=")
        value = value.strip()
        if value and _SUSPICIOUS_VALUE_RE.match(value):
            offenders.append(f"line {lineno}")

    if offenders:
        return _lib.CheckResult(
            ".env.example secret scan",
            _lib.STATUS_FAIL,
            error=f"value(s) that look like real credentials found at {', '.join(offenders)}",
            hint="replace with an empty placeholder (NAME=) and rotate the real credential immediately",
        )
    return _lib.CheckResult(".env.example secret scan", _lib.STATUS_PASS, detail="(no real-looking secrets)")


def run() -> list[_lib.CheckResult]:
    results = []
    results.extend(check_required_vars())
    results.append(check_bridge_url())
    results.append(check_env_example())
    results.append(check_env_example_no_real_secrets())
    return results


def main() -> int:
    _lib.print_section("Environment verification")
    results = run()
    for r in results:
        _lib.print_result(r)
    return 0 if all(r.status != _lib.STATUS_FAIL for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
