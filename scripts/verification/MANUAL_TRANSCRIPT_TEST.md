# Manual known-facts transcript verification

This is a **manual** end-to-end sanity check -- it proves the whole pipeline
(MeetStream capture -> bridge normalization -> transcript -> LlamaIndex
Documents -> retrieval) with content you personally know the right answer
to, so a wrong answer is unambiguous. Nothing in `scripts/verification/`
fakes this for you -- you have to actually say these things in a real
meeting.

## 1. Start a disposable meeting

Start a Google Meet (or Zoom/Teams) you're alone in.

## 2. Dispatch a bot and confirm it joins

```bash
python scripts/verification/live_meetstream_test.py dispatch --meeting-url "<your meeting URL>"
# note the bot_id it prints
python scripts/verification/live_meetstream_test.py status --bot-id <bot_id>
# repeat until status is InMeeting
```

## 3. Say these exact facts out loud, clearly, one at a time

- "The project name is Project Apollo."
- "The launch date is October 14."
- "Anush is responsible for the backend."
- "The approved budget is fifty thousand dollars."

Pause briefly between each one.

## 4. End the meeting

```bash
python scripts/verification/live_meetstream_test.py leave --bot-id <bot_id>
```

## 5. Retrieve and check the transcript

```bash
python scripts/verification/live_meetstream_test.py transcript --bot-id <bot_id>
```

If it prints `NOT READY`, wait a bit and re-run the same command -- MeetStream
processes transcripts after the fact (see `docs/ARCHITECTURE.md` §7); this
script does not poll forever for you.

**Check by eye**: the printed segments should contain all four facts above,
roughly in order. If any are missing, garbled, or a name/number is wrong,
that's a real MeetStream transcription accuracy issue, not a bug in this
integration -- the bridge and reader only pass through whatever MeetStream's
speech-to-text actually produced (see `docs/ARCHITECTURE.md` §3/§7 on why
this project doesn't invent or "correct" transcript content).

## 6. Confirm the LlamaIndex side sees the same content

```bash
python scripts/verification/live_llamaindex_test.py --bot-id <bot_id>
```

Prints sample `Document`s -- confirm the same four facts appear in `text`.

## 7. (Optional) Ask the RAG example real questions

Needs `OPENAI_API_KEY` (see the root `README.md` -- this step is optional
and unrelated to whether the core integration works, which steps 1-6 already
prove without any LLM involved):

```bash
python examples/rag_example.py <bot_id> "What is the project name?"
python examples/rag_example.py <bot_id> "When is the launch date?"
python examples/rag_example.py <bot_id> "Who owns the backend?"
python examples/rag_example.py <bot_id> "What is the approved budget?"
```

Correct answers here confirm retrieval + an LLM's summarization on top of
real MeetStream data -- a good final demo moment, but steps 1-6 are what
actually prove the *integration* (not an LLM's phrasing) works.
