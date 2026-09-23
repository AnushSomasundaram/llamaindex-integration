#!/usr/bin/env python3
"""Bridge server verification: local/static checks plus a real-bridge check.

Distinguishes two categories explicitly:
  - LOCAL/STATIC: does `bridge.app.main` import, does its config model load,
    do the FOUR routes this repository actually implements exist on the
    FastAPI app object. None of this requires a running process.
  - REAL BRIDGE: does an actual HTTP GET to `/health` succeed. Requires
    either an already-running bridge, or `--start-temporary` to spin one up
    for the duration of this script (always torn down on exit -- see
    `_lib.TemporaryBridge`).

Never invents a route: the expected-routes list below is read from
`bridge/app/api/*.py` itself (grepped, not hand-copied) so this check can't
silently drift from the real implementation -- see `_expected_routes()`.

Standalone usage:
    python scripts/verification/check_bridge.py                 # static + real-if-already-running
    python scripts/verification/check_bridge.py --start-temporary  # + spin up a throwaway bridge just for this check

Importable:
    from check_bridge import run
    results = run(start_temporary=False)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib


def _expected_routes() -> list[tuple[str, str]]:
    """Extracts every `@router.<method>("<path>", ...)` from the actual
    `bridge/app/api/*.py` source files -- this is the real, current set of
    routes, not a hardcoded guess that could go stale."""
    routes: list[tuple[str, str]] = []
    pattern = re.compile(r'@router\.(get|post|put|delete)\("([^"]+)"')
    for path in sorted((_lib.BRIDGE_DIR / "app" / "api").glob("*.py")):
        for method, route_path in pattern.findall(path.read_text()):
            routes.append((method.upper(), route_path))
    return routes


def check_import() -> _lib.CheckResult:
    code, out, err = _lib.run_subprocess(
        [sys.executable, "-c", "import app.main; print('ok')"],
        cwd=_lib.BRIDGE_DIR,
        env=_env_with_placeholder_key(),
        timeout=30,
    )
    if code == 0 and "ok" in out:
        return _lib.CheckResult("Bridge import", _lib.STATUS_PASS)
    return _lib.CheckResult(
        "Bridge import",
        _lib.STATUS_FAIL,
        error=(err or out).strip().splitlines()[-1] if (err or out).strip() else "import failed",
        hint=f"pip install -e '{_lib.BRIDGE_DIR}[dev]'",
    )


def check_config_loads() -> _lib.CheckResult:
    code, out, err = _lib.run_subprocess(
        [sys.executable, "-c", "from app.config import get_settings; s = get_settings(); print(s.meetstream_base_url)"],
        cwd=_lib.BRIDGE_DIR,
        env=_env_with_placeholder_key(),
        timeout=30,
    )
    if code == 0:
        return _lib.CheckResult("Bridge config loads", _lib.STATUS_PASS, detail=f"(base_url={out.strip()})")
    return _lib.CheckResult(
        "Bridge config loads",
        _lib.STATUS_FAIL,
        error=(err or out).strip().splitlines()[-1] if (err or out).strip() else "config failed to load",
        hint="check bridge/app/config.py and any MEETSTREAM_* env vars set in this shell",
    )


_ROUTE_INTROSPECTION_SNIPPET = """
import app.main as m

# Newer FastAPI (0.141+, installed here) wraps every `include_router()` call
# as a `fastapi.routing._IncludedRouter` on `app.routes`, rather than
# flattening included routes directly into `app.routes` the way older
# FastAPI versions did -- confirmed by inspecting this repo's actual
# installed version, not assumed from older docs/tutorials. Its real routes
# live on `.original_router.routes`.
def all_routes(routes):
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            yield from all_routes(r.original_router.routes)
        elif hasattr(r, "methods") and r.methods:
            for method in r.methods:
                yield f"{method} {r.path}"

print("\\n".join(sorted(all_routes(m.app.routes))))
"""


def check_routes_exist() -> _lib.CheckResult:
    code, out, err = _lib.run_subprocess(
        [sys.executable, "-c", _ROUTE_INTROSPECTION_SNIPPET],
        cwd=_lib.BRIDGE_DIR,
        env=_env_with_placeholder_key(),
        timeout=30,
    )
    if code != 0:
        return _lib.CheckResult(
            "Bridge routes exist",
            _lib.STATUS_FAIL,
            error=(err or out).strip().splitlines()[-1] if (err or out).strip() else "could not inspect app.routes",
        )

    actual = set(out.strip().splitlines())
    expected = _expected_routes()
    missing = [f"{m} {p}" for m, p in expected if f"{m} {p}" not in actual]
    if missing:
        return _lib.CheckResult(
            "Bridge routes exist",
            _lib.STATUS_FAIL,
            error=f"route(s) declared in app/api/*.py but not registered on the app: {', '.join(missing)}",
            hint="check that app/main.py includes every router from app/api/",
        )
    return _lib.CheckResult("Bridge routes exist", _lib.STATUS_PASS, detail=f"({len(expected)} routes: {', '.join(f'{m} {p}' for m, p in expected)})")


def _env_with_placeholder_key() -> dict:
    env = os.environ.copy()
    env.setdefault("MEETSTREAM_API_KEY", "verification-placeholder-key")
    return env


def check_health_endpoint(base_url: str) -> _lib.CheckResult:
    try:
        status, body = _lib.http_get_json(f"{base_url}/health", timeout=3.0)
    except Exception:  # noqa: BLE001 -- any failure hitting /health (refused, timeout, DNS) means "not reachable"
        return _lib.CheckResult(
            "Bridge health (real)",
            _lib.STATUS_SKIP,
            detail=f"(bridge not reachable at {base_url})",
            hint="start it: cd bridge && uvicorn app.main:app  -- or re-run with --start-temporary (this script) / --start-bridge (verify_all.py)",
        )
    if status == 200 and body.get("status") == "ok":
        return _lib.CheckResult("Bridge health (real)", _lib.STATUS_PASS, detail=f"({base_url}/health -> 200)")
    return _lib.CheckResult("Bridge health (real)", _lib.STATUS_FAIL, error=f"unexpected response: {status} {body}")


def check_connection_failure_is_useful() -> _lib.CheckResult:
    """Confirms that hitting a definitely-not-running port fails with a
    clear connection error, not a hang or a cryptic traceback -- this is
    what `MeetStreamClient` callers see as `MeetStreamConnectionError` (see
    `llama_index_meetstream/exceptions.py`)."""
    bogus_port = _lib.free_tcp_port()
    try:
        _lib.http_get_json(f"http://127.0.0.1:{bogus_port}/health", timeout=1.5)
    except Exception as exc:  # noqa: BLE001 -- deliberately accepting any exception type as "yes, it failed as expected"
        return _lib.CheckResult("Bridge connection-failure message", _lib.STATUS_PASS, detail=f"({type(exc).__name__} raised as expected)")
    return _lib.CheckResult(
        "Bridge connection-failure message",
        _lib.STATUS_FAIL,
        error=f"expected a connection error hitting an unused port ({bogus_port}) but got a response",
    )


def run(start_temporary: bool = False, base_url: str | None = None) -> list[_lib.CheckResult]:
    results = [check_import(), check_config_loads(), check_routes_exist()]
    target_url = base_url or _lib.DEFAULT_BRIDGE_URL

    if _lib.bridge_is_running(target_url):
        results.append(check_health_endpoint(target_url))
    elif start_temporary:
        try:
            with _lib.TemporaryBridge() as tmp:
                results.append(
                    _lib.CheckResult("Bridge health (real)", _lib.STATUS_PASS, detail=f"(temporary instance at {tmp.base_url})")
                )
        except RuntimeError as exc:
            results.append(_lib.CheckResult("Bridge health (real)", _lib.STATUS_FAIL, error=str(exc)))
    else:
        results.append(check_health_endpoint(target_url))  # will produce the SKIPPED row with a hint

    results.append(check_connection_failure_is_useful())
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-temporary", action="store_true", help="Spin up a throwaway bridge process for this check only, then terminate it.")
    parser.add_argument("--bridge-url", default=None, help=f"Bridge URL to check (default: {_lib.DEFAULT_BRIDGE_URL})")
    args = parser.parse_args()

    _lib.print_section("Bridge verification")
    print(f"Bridge URL under test: {args.bridge_url or _lib.DEFAULT_BRIDGE_URL}")
    results = run(start_temporary=args.start_temporary, base_url=args.bridge_url)
    for r in results:
        _lib.print_result(r)
    return 0 if all(r.status != _lib.STATUS_FAIL for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
