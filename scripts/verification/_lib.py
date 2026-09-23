"""Shared helpers for scripts/verification/*.py.

This is a dev-only verification toolkit, not part of any published package --
it is never imported by `bridge/` or `llama_index_meetstream/`. Every script
in this directory imports it the same way:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _lib

Centralizing this here (CheckResult printing, subprocess running, bridge
liveness checks, temp-venv helpers) means the ~15 verification scripts in
this directory don't each reimplement their own version of "run pytest and
parse the summary line" or "is the bridge up." Business logic itself
(MeetStream response parsing, tool schemas, Document construction) is never
duplicated here -- every real check imports the actual project code
(`app.*`, `llama_index_meetstream`) and inspects it directly, per this
suite's own ground rule of not re-implementing what it's trying to verify.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_DIR = REPO_ROOT / "bridge"
LLAMAINDEX_DIR = REPO_ROOT

DEFAULT_BRIDGE_URL = os.environ.get("MEETSTREAM_BRIDGE_URL", "http://localhost:8000").rstrip("/")

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIP = "SKIPPED"
STATUS_NOTRUN = "NOT RUN"

_ALL_STATUSES = (STATUS_PASS, STATUS_FAIL, STATUS_SKIP, STATUS_NOTRUN)


@dataclass
class CheckResult:
    """One row of verification output.

    `status` must be one of `STATUS_PASS`/`STATUS_FAIL`/`STATUS_SKIP`/
    `STATUS_NOTRUN` -- callers never invent their own status strings, so a
    report generator or CI step can rely on this closed set.
    """

    name: str
    status: str
    detail: str = ""  # short suffix shown after the status, e.g. "(24 tests)"
    error: str = ""  # the *actual* error text -- only shown/stored on FAIL
    hint: str = ""  # a concrete next diagnostic step -- shown on FAIL/SKIP

    def __post_init__(self) -> None:
        if self.status not in _ALL_STATUSES:
            raise ValueError(f"Invalid CheckResult status {self.status!r} for {self.name!r}")

    def line(self) -> str:
        suffix = f" {self.detail}" if self.detail else ""
        # `ljust` (rather than an f-string width spec) guarantees at least
        # one separating space even when `name` is longer than the target
        # column width, instead of running straight into `status`.
        return f"{self.name.ljust(32)} {self.status}{suffix}"


def print_result(r: CheckResult) -> None:
    print(r.line())
    if r.status == STATUS_FAIL and r.error:
        print(f"    error: {r.error}")
    if r.status in (STATUS_FAIL, STATUS_SKIP) and r.hint:
        print(f"    next step: {r.hint}")


def print_section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


# --------------------------------------------------------------------------
# HTTP / bridge liveness
# --------------------------------------------------------------------------


def http_get_json(url: str, timeout: float = 2.0) -> tuple[int, dict]:
    """Minimal stdlib GET returning (status_code, parsed_json_body).

    Deliberately uses `urllib` (stdlib), not `httpx`/`requests` -- this
    verification suite must be able to at least *report* "bridge deps aren't
    installed" even when the framework/bridge packages themselves aren't
    importable yet.
    """
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, (json.loads(body) if body else {})


def http_request_json(method: str, url: str, json_body: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    """Minimal stdlib HTTP request (GET/POST) with a JSON body and JSON
    response, returning (status_code, parsed_body_or_error_body).

    Used by `live_meetstream_test.py`, which talks to the bridge directly
    and deliberately does NOT import `llama_index_meetstream` -- it verifies
    the BRIDGE and real MeetStream, a layer below the framework package, so
    it shouldn't need it installed to run. A non-2xx response still returns
    its parsed JSON body (the bridge's `{"error": {"code", "message"}}`
    shape) rather than raising, since that body is exactly what the caller
    needs to report.
    """
    data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body) if body else {}
        except json.JSONDecodeError:
            return exc.code, {"raw_body": body}


def bridge_is_running(base_url: str = DEFAULT_BRIDGE_URL, timeout: float = 1.5) -> bool:
    """True if something answering like this bridge is already listening at
    `base_url`. Used everywhere to decide whether to run "real bridge"
    checks against an already-running instance, spin up a temporary one, or
    skip them."""
    try:
        status, body = http_get_json(f"{base_url}/health", timeout=timeout)
        return status == 200 and body.get("status") == "ok"
    except Exception:  # noqa: BLE001 -- any failure here (DNS, refused, timeout, bad JSON, ...) means "not running"
        return False


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TemporaryBridge:
    """Starts the real `bridge/app/main.py` FastAPI app, as a real subprocess
    (`uvicorn`), on a free local port, for the lifetime of a `with` block --
    then always terminates it, even on error.

    Runs against the CURRENT Python environment (`sys.executable`), not a
    freshly created venv -- this suite assumes you've already run
    `pip install -e bridge[dev]` per docs/DEVELOPMENT.md, matching how the
    bridge is actually run day to day. If bridge deps aren't importable, the
    subprocess exits immediately and `__enter__` raises with the captured
    output, rather than hanging.

    Uses a placeholder `MEETSTREAM_API_KEY` unless one is already set in the
    environment -- fine for STRUCTURAL checks (does the app boot, do routes
    exist, does /health respond) since none of those make a real MeetStream
    call. This class is never used for real MeetStream verification -- see
    `live_meetstream_test.py`, which requires your real key and talks to
    whatever bridge is already running (never starts its own).
    """

    def __init__(self, api_key: str = "verification-placeholder-key", startup_timeout: float = 10.0):
        self.port = free_tcp_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._api_key = api_key
        self._startup_timeout = startup_timeout
        self._proc: subprocess.Popen | None = None

    def __enter__(self) -> TemporaryBridge:  # noqa: PYI034 -- keeps this file's minimum-version story simple; `Self` needs 3.11+.
        env = os.environ.copy()
        env.setdefault("MEETSTREAM_API_KEY", self._api_key)
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=str(BRIDGE_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + self._startup_timeout
        while time.time() < deadline:
            if bridge_is_running(self.base_url, timeout=0.5):
                return self
            if self._proc.poll() is not None:
                output = self._proc.stdout.read() if self._proc.stdout else ""
                raise RuntimeError(f"Temporary bridge process exited early (code {self._proc.returncode}):\n{output}")
            time.sleep(0.25)
        self.__exit__(None, None, None)
        raise RuntimeError(f"Temporary bridge did not become healthy within {self._startup_timeout}s")

    def __exit__(self, *exc_info: object) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)


# --------------------------------------------------------------------------
# Subprocess / pytest / ruff helpers
# --------------------------------------------------------------------------


def run_subprocess(cmd: list[str], cwd: Path | None = None, env: dict | None = None, timeout: float = 600) -> tuple[int, str, str]:
    # check=False deliberately: every caller inspects the returncode itself
    # to build a PASS/FAIL CheckResult with useful detail -- a raised
    # CalledProcessError here would just have to be caught and unpacked
    # again one level up.
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    return result.returncode, result.stdout, result.stderr


def parse_pytest_summary(output: str) -> dict:
    """Extracts real pass/fail/error/skip counts from pytest's own final
    summary line (e.g. "24 passed, 1 warning in 1.28s" or "2 failed, 22
    passed in 1.0s"). Never hardcodes a count -- if pytest's output format
    changes and nothing matches, every count comes back 0 and the caller's
    own PASS/FAIL logic (driven by pytest's exit code, not these counts)
    still reflects reality; the counts are for the human-readable `detail`
    string only.
    """

    def _count(word: str) -> int:
        m = re.search(rf"(\d+) {word}", output)
        return int(m.group(1)) if m else 0

    return {
        "passed": _count("passed"),
        "failed": _count("failed"),
        "error": _count("error"),
        "skipped": _count("skipped"),
    }


def run_pytest(directory: Path) -> tuple[CheckResult, str]:
    """Runs `pytest -q` in `directory` using the CURRENT interpreter (so it
    exercises whatever's actually installed, editable or otherwise -- not a
    separate hardcoded pytest binary). Returns a `CheckResult` plus the full
    combined stdout+stderr for a report file to keep, if needed."""
    label = f"{directory.name} tests"
    try:
        code, out, err = run_subprocess([sys.executable, "-m", "pytest", "-q"], cwd=directory, timeout=300)
    except FileNotFoundError as exc:
        return CheckResult(label, STATUS_FAIL, error=str(exc), hint=f"pip install -e '{directory}[dev]'"), ""
    except subprocess.TimeoutExpired:
        return CheckResult(label, STATUS_FAIL, error="pytest timed out after 300s"), ""

    combined = out + err
    counts = parse_pytest_summary(combined)
    total = counts["passed"] + counts["failed"] + counts["error"]

    if code == 0 and total > 0:
        return CheckResult(label, STATUS_PASS, detail=f"({counts['passed']} tests)"), combined
    if total == 0:
        return (
            CheckResult(
                label,
                STATUS_FAIL,
                error="pytest ran but no tests were collected (0 passed/failed/error)",
                hint=f"pip install -e '{directory}[dev]' then re-run `pytest -q` in {directory} manually",
            ),
            combined,
        )
    return (
        CheckResult(
            label,
            STATUS_FAIL,
            detail=f"({counts['failed'] + counts['error']} failed / {total} total)",
            error=combined.strip().splitlines()[-1] if combined.strip() else "pytest failed",
            hint=f"run `cd {directory} && pytest -q` directly to see full failures",
        ),
        combined,
    )


def run_ruff(directory: Path, targets: list[str]) -> tuple[CheckResult, str]:
    label = f"{directory.name} ruff"
    try:
        code, out, err = run_subprocess([sys.executable, "-m", "ruff", "check", *targets], cwd=directory, timeout=60)
    except FileNotFoundError as exc:
        return CheckResult(label, STATUS_FAIL, error=str(exc), hint=f"pip install -e '{directory}[dev]'"), ""
    combined = out + err
    if code == 0:
        return CheckResult(label, STATUS_PASS), combined
    return (
        CheckResult(label, STATUS_FAIL, error=combined.strip().splitlines()[-1] if combined.strip() else "ruff failed"),
        combined,
    )


# --------------------------------------------------------------------------
# Fresh-venv helpers (used by check_packaging.py)
# --------------------------------------------------------------------------


def create_venv(path: Path) -> Path:
    """Creates a throwaway venv at `path` using whichever tool is available
    (`uv venv` if present -- much faster -- else stdlib `venv`), and returns
    the path to its `python` executable."""
    if _uv_available():
        run_subprocess(["uv", "venv", str(path)], timeout=60)
    else:
        run_subprocess([sys.executable, "-m", "venv", str(path)], timeout=120)
    py = path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        raise RuntimeError(f"venv creation at {path} did not produce an interpreter at {py}")
    return py


def _uv_available() -> bool:
    try:
        code, _, _ = run_subprocess(["uv", "--version"], timeout=10)
        return code == 0
    except FileNotFoundError:
        return False


def pip_install(python: Path, args: list[str], timeout: float = 300) -> tuple[int, str, str]:
    if _uv_available():
        return run_subprocess(["uv", "pip", "install", "--python", str(python), *args], timeout=timeout)
    return run_subprocess([str(python), "-m", "pip", "install", *args], timeout=timeout)


def build_wheel(package_dir: Path) -> tuple[CheckResult, Path | None]:
    """Builds a wheel for `package_dir` with the `build` module and returns
    (result, path_to_wheel_or_None). Cleans any pre-existing `dist/` first so
    a stale wheel from an earlier manual `python -m build` can't be mistaken
    for a fresh one."""
    dist_dir = package_dir / "dist"
    label = f"{package_dir.name} wheel build"
    if dist_dir.exists():
        for f in dist_dir.iterdir():
            f.unlink()
    code, out, err = run_subprocess([sys.executable, "-m", "build", "--wheel"], cwd=package_dir, timeout=180)
    if code != 0:
        combined = out + err
        hint = "pip install build" if "No module named build" in combined else ""
        return CheckResult(label, STATUS_FAIL, error=combined.strip().splitlines()[-1] if combined.strip() else "build failed", hint=hint), None
    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        return CheckResult(label, STATUS_FAIL, error="build exited 0 but produced no .whl file"), None
    return CheckResult(label, STATUS_PASS, detail=f"({wheels[-1].name})"), wheels[-1]


# --------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------


def git_available() -> bool:
    try:
        code, _, _ = run_subprocess(["git", "--version"], timeout=5)
        return code == 0
    except FileNotFoundError:
        return False


def git(args: list[str], cwd: Path = REPO_ROOT) -> tuple[int, str, str]:
    return run_subprocess(["git", *args], cwd=cwd, timeout=30)
