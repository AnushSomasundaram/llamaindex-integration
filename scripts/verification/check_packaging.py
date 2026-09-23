#!/usr/bin/env python3
"""Packaging/build verification for `llama-index-meetstream`: builds a real
wheel, installs it into a completely fresh temporary virtual environment
(never the environment this script itself runs in), imports the public API
from THAT installed copy, and confirms the
import actually came from the installed site-packages -- not this repo's
source tree (which would happen if the fresh venv somehow still saw the repo
on `sys.path`, silently passing even with a broken package).

Also checks the built wheel's file listing doesn't contain anything it
shouldn't (`.env`, `__pycache__`, `.venv`, other repo files) -- see
`_bad_wheel_members()`.

Never publishes anything anywhere -- only `python -m build` (local) and
`pip install` into a throwaway, deleted-at-the-end venv.

Standalone usage:
    python scripts/verification/check_packaging.py

Importable:
    from check_packaging import run
    results = run()
"""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib

_PACKAGES = [
    (_lib.LLAMAINDEX_DIR, "llama_index_meetstream", "MeetStreamReader"),
]

# Anything matching these should NEVER show up inside a built wheel.
_FORBIDDEN_WHEEL_PATTERNS = [".env", "__pycache__", ".venv", ".git", "dist/", ".ruff_cache", ".pytest_cache"]


def _bad_wheel_members(wheel_path: Path) -> list[str]:
    with zipfile.ZipFile(wheel_path) as zf:
        return [name for name in zf.namelist() if any(p in name for p in _FORBIDDEN_WHEEL_PATTERNS)]


def _package_metadata_ok(wheel_path: Path) -> tuple[bool, str]:
    with zipfile.ZipFile(wheel_path) as zf:
        metadata_files = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        if not metadata_files:
            return False, "no *.dist-info/METADATA found in wheel"
        metadata = zf.read(metadata_files[0]).decode("utf-8", errors="replace")
        required_fields = ["Name:", "Version:", "Requires-Python:"]
        missing = [f for f in required_fields if f not in metadata]
        if missing:
            return False, f"METADATA missing field(s): {missing}"
        return True, metadata.splitlines()[0:3]


def verify_one_package(package_dir: Path, import_name: str, key_symbol: str) -> list[_lib.CheckResult]:
    results: list[_lib.CheckResult] = []
    label_prefix = package_dir.name

    # 1. Build the wheel (and, per the spec, the sdist too -- both are
    # configured via [build-system]/hatchling in this project's pyproject.toml).
    build_result, wheel_path = _lib.build_wheel(package_dir)
    results.append(build_result)
    if wheel_path is None:
        return results

    code, out, err = _lib.run_subprocess([sys.executable, "-m", "build", "--sdist"], cwd=package_dir, timeout=180)
    sdist_files = list((package_dir / "dist").glob("*.tar.gz"))
    if code == 0 and sdist_files:
        results.append(_lib.CheckResult(f"{label_prefix} sdist build", _lib.STATUS_PASS, detail=f"({sdist_files[-1].name})"))
    else:
        results.append(_lib.CheckResult(f"{label_prefix} sdist build", _lib.STATUS_FAIL, error=(out + err).strip().splitlines()[-1] if (out + err).strip() else "sdist build failed"))

    # 2. Package metadata sanity (Name/Version/Requires-Python present).
    ok, info = _package_metadata_ok(wheel_path)
    results.append(
        _lib.CheckResult(f"{label_prefix} package metadata", _lib.STATUS_PASS if ok else _lib.STATUS_FAIL, detail=str(info) if ok else "", error="" if ok else str(info))
    )

    # 3. Wheel contents don't leak anything they shouldn't.
    bad_members = _bad_wheel_members(wheel_path)
    if bad_members:
        results.append(
            _lib.CheckResult(
                f"{label_prefix} wheel contents clean",
                _lib.STATUS_FAIL,
                error=f"wheel contains disallowed path(s): {bad_members[:5]}",
                hint="check [tool.hatch.build.targets.wheel] packages= in pyproject.toml",
            )
        )
    else:
        results.append(_lib.CheckResult(f"{label_prefix} wheel contents clean", _lib.STATUS_PASS))

    # 4. Fresh temporary venv, install the wheel, import from it, confirm
    # the import is NOT resolving to this repo's own source directory.
    with tempfile.TemporaryDirectory(prefix="meetstream-verify-venv-") as tmp_str:
        venv_dir = Path(tmp_str) / "venv"
        try:
            python = _lib.create_venv(venv_dir)
        except Exception as exc:  # noqa: BLE001 -- venv/uv creation can fail in many ways; all of them mean this check FAILs
            results.append(_lib.CheckResult(f"{label_prefix} clean install", _lib.STATUS_FAIL, error=f"could not create temp venv: {exc}"))
            return results

        code, out, err = _lib.pip_install(python, [str(wheel_path)], timeout=300)
        if code != 0:
            results.append(
                _lib.CheckResult(
                    f"{label_prefix} clean install",
                    _lib.STATUS_FAIL,
                    error=(out + err).strip().splitlines()[-1] if (out + err).strip() else "pip install failed",
                )
            )
            return results

        probe = (
            f"import {import_name}, os\n"
            f"assert hasattr({import_name}, {key_symbol!r}), 'missing public symbol {key_symbol}'\n"
            f"path = os.path.abspath({import_name}.__file__)\n"
            f"print('VERSION=' + getattr({import_name}, '__version__', 'unknown'))\n"
            f"print('PATH=' + path)\n"
        )
        code, out, err = _lib.run_subprocess(
            [str(python), "-c", probe],
            cwd=Path.home(),  # deliberately NOT the repo -- proves the import can't fall back to repo source on cwd
            timeout=30,
        )
        if code != 0:
            results.append(
                _lib.CheckResult(
                    f"{label_prefix} clean install",
                    _lib.STATUS_FAIL,
                    error=(err or out).strip().splitlines()[-1] if (err or out).strip() else "import from installed wheel failed",
                )
            )
            return results

        info_lines = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
        installed_path = Path(info_lines.get("PATH", ""))
        version = info_lines.get("VERSION", "unknown")

        if _lib.REPO_ROOT in installed_path.parents or installed_path == _lib.REPO_ROOT:
            results.append(
                _lib.CheckResult(
                    f"{label_prefix} import resolves to installed wheel (not repo source)",
                    _lib.STATUS_FAIL,
                    error=f"import resolved to {installed_path}, which is inside the repo -- the venv is not actually isolated",
                )
            )
        else:
            results.append(
                _lib.CheckResult(
                    f"{label_prefix} import resolves to installed wheel (not repo source)",
                    _lib.STATUS_PASS,
                    detail=f"({installed_path})",
                )
            )

        results.append(_lib.CheckResult(f"{label_prefix} clean install", _lib.STATUS_PASS, detail=f"(v{version})"))

    return results


def run() -> list[_lib.CheckResult]:
    results = []
    for package_dir, import_name, key_symbol in _PACKAGES:
        results.extend(verify_one_package(package_dir, import_name, key_symbol))
    return results


def main() -> int:
    _lib.print_section("Packaging / clean-install verification")
    results = run()
    for r in results:
        _lib.print_result(r)
    return 0 if all(r.status != _lib.STATUS_FAIL for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
