# Demo readiness checklist

Run through this before demoing to your manager. Check off each box as you
verify it -- don't check a box because you assume it's fine, check it
because a script or a manual step just confirmed it.

## Pre-demo (do this well before the demo, not 5 minutes prior)

- [ ] Bridge running: `cd bridge && uvicorn app.main:app` (pointed at your real `MEETSTREAM_API_KEY`)
- [ ] Health endpoint works: `curl http://localhost:8000/health` -> `{"status":"ok"}`
- [ ] API credentials loaded: `python scripts/verification/check_environment.py` shows `MEETSTREAM_API_KEY SET`
- [ ] Live bot dispatch verified: `python scripts/verification/live_meetstream_test.py dispatch --meeting-url <url>` -> bot joins a real meeting you watched
- [ ] Known-working `bot_id` saved somewhere you can paste it from (see "Fallback" below)
- [ ] Live transcript retrieved: `python scripts/verification/live_meetstream_test.py transcript --bot-id <bot_id>` -> real segments printed
- [ ] LlamaIndex Reader verified: `python scripts/verification/live_llamaindex_test.py --bot-id <bot_id>` -> all PASS
- [ ] LlamaIndex tools verified: `python scripts/verification/live_llamaindex_tools.py list` and at least one `invoke` against the real bridge
- [ ] LlamaIndex agent verified: `python scripts/verification/live_llamaindex_agent.py --bot-id <bot_id>` -> all PASS (needs `OPENAI_API_KEY`)
- [ ] LlamaIndex agent demo ready: `examples/agent_example.py` runs (needs `OPENAI_API_KEY`) -- run it once before the demo, not for the first time live
- [ ] Tests passing: `python scripts/verification/check_tests.py` -> all PASS, real counts shown
- [ ] Package builds: `python scripts/verification/check_packaging.py` -> wheel builds
- [ ] Clean installation verified: same run, both "clean install" and "resolves to installed wheel" rows PASS
- [ ] No secrets committed: `python scripts/verification/check_git_security.py` -> all PASS
- [ ] Fallback `bot_id`/transcript available in case the live meeting demo fails during the actual demo (see below)

## Fallback plan

Live software + a live video call in front of your manager is two things
that can go wrong at once. Before the demo:

1. Run the full manual sequence in `MANUAL_TRANSCRIPT_TEST.md` once, ahead of
   time, and **write down the resulting `bot_id`** somewhere you can paste
   from during the demo (a notes file, not memory).
2. If live dispatch fails or a meeting won't cooperate during the actual
   demo, fall back to that already-known-good `bot_id` for the
   transcript/reader/tools portions of the demo -- everything downstream of
   dispatch (`status`, `leave`, `transcript`, `live_llamaindex_test.py`, the
   RAG example) works identically against an older bot_id as a fresh one,
   since MeetStream retains the data.
3. Have `scripts/verification/verify_all.py`'s last full-green run visible
   (or a saved `verification-report.md`) as evidence everything was working
   shortly before the demo, independent of whatever happens live.

## Recommended 5-minute demo sequence

1. **(30s)** Show the bridge is up: `curl http://localhost:8000/health`.
2. **(1 min)** Dispatch a bot live: `live_meetstream_test.py dispatch --meeting-url <url>`, show it join the meeting on screen.
3. **(1 min)** Say something in the meeting, then `live_meetstream_test.py leave --bot-id <id>` and `transcript --bot-id <id>` to show the real captured text.
4. **(1.5 min)** Run `examples/agent_example.py` live -- ask it to summarize the meeting, showing the agent calling `get_meeting_transcript` on its own.
5. **(1 min)** If time allows, `rag_example.py` with one of the known-facts questions from `MANUAL_TRANSCRIPT_TEST.md` for a clean, verifiable Q&A moment.

If step 2 or 3 misbehaves live, switch immediately to the fallback `bot_id`
from your pre-demo run and continue at step 4 -- don't burn demo time
debugging a live meeting connection in front of your manager.
