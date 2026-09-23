# scripts/verification/

A verification/smoke-test suite for the MeetStream bridge + LlamaIndex
integration, separate from (and complementary to) each project's own
`tests/` (`bridge/tests`, `tests/`) -- those are unit tests run by `pytest`;
this directory is a demo-readiness toolkit you run directly with `python`.

## Quick start

```bash
# Everything that doesn't require joining a real meeting (default):
python scripts/verification/verify_all.py

# Just one category:
python scripts/verification/verify_all.py --local
python scripts/verification/verify_all.py --packaging
python scripts/verification/verify_all.py --live              # never dispatches a bot
python scripts/verification/verify_all.py --live --bot-id <id> # real, read-only status+transcript check

# Write a report:
python scripts/verification/verify_all.py --report
```

## Files

| File | Category | What it checks |
|---|---|---|
| `_lib.py` | (shared) | `CheckResult`, subprocess/pytest/ruff helpers, bridge liveness, temp-venv helpers -- not a check itself |
| `check_environment.py` | Local/static | Required env vars set (never printed), `.env.example` completeness and secret-scan |
| `check_bridge.py` | Local/static + Real bridge | Bridge imports, config loads, real routes exist on the app; `/health` if a bridge is reachable (or `--start-temporary` to spin one up just for this check) |
| `check_tests.py` | Mocked automated tests | Runs the 2 existing `pytest` suites + `ruff`, reports REAL counts |
| `check_llamaindex.py` | Mocked / LlamaIndex | Imports, client, reader (real code + mocked bridge), all 6 tools + direct invocation |
| `check_packaging.py` | Packaging | Wheel + sdist build, metadata, wheel contents clean, fresh-venv install, import resolves to the installed wheel (not repo source) |
| `check_git_security.py` | Git/security | No `.env`/junk tracked, `.gitignore` coverage, no secret-shaped values in tracked or staged content |
| `live_meetstream_test.py` | **Real MeetStream API** | `dispatch` / `status` / `leave` / `transcript` against a real, already-running bridge + real MeetStream. Never run automatically. |
| `live_llamaindex_test.py` | **Real LlamaIndex** | `MeetStreamReader` against a real, already-captured transcript (needs `--bot-id`) |
| `live_llamaindex_tools.py` | **Real LlamaIndex tools** | `list` real tool schemas, `invoke <tool> --json '...'` directly against the real bridge -- no LLM involved |
| `live_llamaindex_agent.py` | **Real LlamaIndex agent** | A real tool-calling LLM, given the real `get_meetstream_tools()`, correctly decides to call `get_meeting_transcript` with the right `meeting_id` and produces a real final answer -- needs `OPENAI_API_KEY` |
| `verify_all.py` | (runner) | Runs the above (never the `live_*` dispatch-a-bot step) and prints one summary |
| `DEMO_CHECKLIST.md` | -- | Pre-demo checklist + fallback plan + 5-minute demo sequence |
| `MANUAL_TRANSCRIPT_TEST.md` | -- | Manual known-facts transcript test guide (say 4 facts in a real meeting, verify they come back correctly) |

## The six categories, and why they're kept separate

1. **Local/static** -- imports, config, route lists. No process, no network.
2. **Mocked automated tests** -- the repo's own `pytest` suites; HTTP is mocked with `respx`.
3. **Real bridge verification** -- an actual HTTP call to a real bridge process's `/health`, but the bridge itself may be using a placeholder key (no real MeetStream call happens).
4. **Real MeetStream API verification** -- `live_meetstream_test.py` only; needs your real key and a bridge actually configured with it.
5. **LlamaIndex integration verification** -- `check_llamaindex.py` (mocked) / `live_llamaindex_test.py` + `live_llamaindex_tools.py` + `live_llamaindex_agent.py` (real).
6. **Packaging/install verification** -- `check_packaging.py`.

Every script's output tells you which of these it just did -- never assume a
green summary line means "verified against real MeetStream" unless the
script says so explicitly.
