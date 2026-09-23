#!/usr/bin/env python3
"""Git / repository security sanity check.

Read-only: reports findings, never modifies or deletes anything. If it finds
something concerning (e.g. `.env` actually tracked by git), it tells you and
stops there -- you decide what to do about it.

Standalone usage:
    python scripts/verification/check_git_security.py

Importable:
    from check_git_security import run
    results = run()
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib

# Filenames/patterns that should never be tracked by git in this repo.
_SHOULD_NEVER_BE_TRACKED = [
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)\.env\.[^.]*$"),  # .env.local, .env.production, etc -- NOT .env.example
    re.compile(r"__pycache__/"),
    re.compile(r"(^|/)\.venv/"),
    re.compile(r"(^|/)dist/"),
    re.compile(r"\.egg-info/"),
    re.compile(r"\.ruff_cache/"),
    re.compile(r"\.pytest_cache/"),
]

# A hard exception -- .env.example is meant to be tracked.
_ALWAYS_ALLOWED = {".env.example"}

# Crude content patterns that suggest a real secret got committed. Matches
# the same MeetStream key shape this project has actually seen
# (`ms_<random>`), plus a couple of other common provider key shapes, so a
# genuine leak doesn't slip past just because it isn't a MeetStream key.
_SECRET_VALUE_RE = re.compile(r"\b(ms_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{12,})\b")


def check_git_repo_present() -> _lib.CheckResult:
    if not _lib.git_available():
        return _lib.CheckResult("git available", _lib.STATUS_FAIL, error="`git` not found on PATH")
    code, out, err = _lib.git(["rev-parse", "--is-inside-work-tree"])
    if code != 0 or out.strip() != "true":
        return _lib.CheckResult("git repository", _lib.STATUS_FAIL, error=(err or out).strip())
    return _lib.CheckResult("git repository", _lib.STATUS_PASS)


def check_no_forbidden_paths_tracked() -> _lib.CheckResult:
    code, out, err = _lib.git(["ls-files"])
    if code != 0:
        return _lib.CheckResult("no secrets/junk tracked by git", _lib.STATUS_FAIL, error=(err or out).strip())

    tracked = out.strip().splitlines()
    offenders = []
    for path in tracked:
        if Path(path).name in _ALWAYS_ALLOWED:
            continue
        if any(pattern.search(path) for pattern in _SHOULD_NEVER_BE_TRACKED):
            offenders.append(path)

    if offenders:
        return _lib.CheckResult(
            "no secrets/junk tracked by git",
            _lib.STATUS_FAIL,
            error=f"git is tracking file(s) that should be gitignored: {offenders}",
            hint="git rm --cached <path> for each, and confirm .gitignore covers it (do not run this automatically -- ask before removing tracked history)",
        )
    return _lib.CheckResult("no secrets/junk tracked by git", _lib.STATUS_PASS, detail=f"({len(tracked)} files tracked)")


def check_gitignore_covers_expected_patterns() -> _lib.CheckResult:
    path = _lib.REPO_ROOT / ".gitignore"
    if not path.exists():
        return _lib.CheckResult(".gitignore covers expected patterns", _lib.STATUS_FAIL, error=".gitignore does not exist")
    text = path.read_text()
    required_substrings = ["__pycache__", ".venv", ".env", "dist/", ".egg-info", ".pytest_cache", ".ruff_cache"]
    missing = [s for s in required_substrings if s not in text]
    if missing:
        return _lib.CheckResult(
            ".gitignore covers expected patterns",
            _lib.STATUS_FAIL,
            error=f"missing pattern(s): {missing}",
        )
    return _lib.CheckResult(".gitignore covers expected patterns", _lib.STATUS_PASS)


def check_no_secret_looking_content_in_tracked_files() -> _lib.CheckResult:
    """Greps every git-tracked, non-binary file for a value shaped like a
    real API key. Deliberately scans FILE CONTENT (not just filenames) --
    someone could paste a real key into an otherwise-innocuous-looking file
    (a README, a script, a committed log)."""
    code, out, _ = _lib.git(["ls-files"])
    if code != 0:
        return _lib.CheckResult("no secret-shaped values in tracked file content", _lib.STATUS_SKIP, hint="git ls-files failed")

    offenders = []
    for rel_path in out.strip().splitlines():
        full_path = _lib.REPO_ROOT / rel_path
        if not full_path.is_file() or full_path.name in _ALWAYS_ALLOWED:
            continue
        try:
            text = full_path.read_text(errors="ignore")
        except (OSError, UnicodeError):
            # Binary file, permission error, or similar -- not scannable as
            # text, so skip it rather than fail the whole scan over one file.
            continue
        if _SECRET_VALUE_RE.search(text):
            offenders.append(rel_path)

    if offenders:
        return _lib.CheckResult(
            "no secret-shaped values in tracked file content",
            _lib.STATUS_FAIL,
            error=f"file(s) contain a value shaped like a real API key: {offenders}",
            hint="rotate that credential immediately, then remove it from the file (and git history if already pushed)",
        )
    return _lib.CheckResult("no secret-shaped values in tracked file content", _lib.STATUS_PASS)


def check_working_tree_secrets_not_staged() -> _lib.CheckResult:
    """Checks currently staged (but not yet committed) changes for the same
    secret-shaped pattern -- catches a mistake before it becomes a commit."""
    code, out, _ = _lib.git(["diff", "--cached", "--unified=0"])
    if code != 0:
        return _lib.CheckResult("no secret-shaped values staged", _lib.STATUS_SKIP, hint="git diff --cached failed")
    added_lines = "\n".join(line for line in out.splitlines() if line.startswith("+") and not line.startswith("+++"))
    if _SECRET_VALUE_RE.search(added_lines):
        return _lib.CheckResult(
            "no secret-shaped values staged",
            _lib.STATUS_FAIL,
            error="staged changes contain a value shaped like a real API key",
            hint="git reset the offending file before committing",
        )
    return _lib.CheckResult("no secret-shaped values staged", _lib.STATUS_PASS)


def run() -> list[_lib.CheckResult]:
    results = [check_git_repo_present()]
    if results[0].status == _lib.STATUS_FAIL:
        return results
    results.append(check_no_forbidden_paths_tracked())
    results.append(check_gitignore_covers_expected_patterns())
    results.append(check_no_secret_looking_content_in_tracked_files())
    results.append(check_working_tree_secrets_not_staged())
    return results


def main() -> int:
    _lib.print_section("Git / repository security sanity check")
    results = run()
    for r in results:
        _lib.print_result(r)
    return 0 if all(r.status != _lib.STATUS_FAIL for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
