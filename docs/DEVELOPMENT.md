# Development Guide

Step-by-step setup for working on this repository. Assumes you know Python but not
necessarily packaging — every `pip`/`uv` command below is spelled out in full.

## 1. Clone the repository

```bash
git clone <repo-url> llamaindex-meetstream
cd llamaindex-meetstream
```

## 2. Create a virtual environment

Any of these work; examples below assume `uv` (fast, no separate `venv` step needed) but
plain `venv`/`pip` works identically.

```bash
uv venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

## 3. Install dependencies

This repo has **two independent Python projects** (`bridge/` and the `llama_index_meetstream`
package at the repo root), each with its own `pyproject.toml`. Install each in editable mode
with its `dev` extra:

```bash
uv pip install -e "bridge[dev]"
uv pip install -e ".[dev]"
```

Add `[examples]` instead of/alongside `[dev]` on the root package if you also want to run
the example scripts (pulls in `llama-index-llms-openai`/`llama-index-embeddings-openai`).

## 4. Configure `.env`

```bash
cp .env.example .env
```

Fill in `MEETSTREAM_API_KEY` with a real MeetStream key to run the bridge against real
MeetStream, or leave it as any placeholder string to just run the test suites (all tests
mock MeetStream/the bridge at the HTTP layer — see "Testing" below). Fill in
`OPENAI_API_KEY` only if you plan to run the RAG/agent example scripts.

## 5. Run the bridge

```bash
cd bridge
export $(grep -v '^#' ../.env | xargs)   # or just `export MEETSTREAM_API_KEY=...` directly
uvicorn app.main:app --reload
```

Confirm it's up: `curl http://localhost:8000/health` → `{"status": "ok"}`.

## 6. Run the tests

Each project's tests run independently and require no network access or running bridge —
everything is mocked at the `httpx` transport layer with `respx`.

```bash
(cd bridge && pytest)
pytest
```

## 7. Run the reader example

Requires the bridge running (step 5) against a **real** MeetStream account, plus a
`meeting_id` for a meeting whose bot has already finished and transcribed.

```bash
python examples/reader_example.py <meeting_id>
```

## 8. Run the LlamaIndex examples

```bash
pip install -e ".[examples]"
export OPENAI_API_KEY=...
python examples/rag_example.py <meeting_id> "What deadline was discussed?"
python examples/agent_example.py
```

## 9. Build the package

```bash
python -m build
```

(`python -m pip install build` first if you don't already have the `build` tool.) Produces
a wheel + sdist in `dist/`. Verify a wheel installs cleanly in an isolated environment before
trusting it:

```bash
uv venv /tmp/verify-llama-index-meetstream
/tmp/verify-llama-index-meetstream/bin/pip install dist/*.whl
/tmp/verify-llama-index-meetstream/bin/python -c "from llama_index_meetstream import MeetStreamReader; print('ok')"
```

## Linting

```bash
(cd bridge && ruff check app tests)
ruff check llama_index_meetstream tests examples
```

## Publishing (documented, not automated)

This repository does not auto-publish to PyPI. To publish the package manually once you have
PyPI credentials configured:

```bash
python -m build
python -m twine upload dist/*
```

Bump `version` in `pyproject.toml` first. `.github/workflows/ci.yml` runs install/lint/test/
build on every push but does not upload anywhere — see that file's comments for how you'd
wire in a real publish step (a PyPI API token secret and a `twine upload` step gated on a git
tag) once this project is ready to publish for real.
