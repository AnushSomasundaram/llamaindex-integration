"""Shared test fixtures for the bridge.

Every test mocks MeetStream at the `httpx` transport layer with `respx` --
nothing here ever makes a real network call, per this project's testing
requirements (see docs/DEVELOPMENT.md "Testing").
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import respx
from fastapi.testclient import TestClient

os.environ.setdefault("MEETSTREAM_API_KEY", "test-api-key")

MEETSTREAM_BASE_URL = "https://api.meetstream.ai/api/v1"


@pytest.fixture
def meetstream_mock() -> Iterator[respx.MockRouter]:
    """A respx router pre-scoped to MeetStream's base URL. Individual tests
    register the specific routes (`.post("/bots/create_bot")`, etc.) they need."""
    with respx.mock(base_url=MEETSTREAM_BASE_URL, assert_all_called=False) as router:
        yield router


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A FastAPI `TestClient` for the bridge app.

    Imported lazily (inside the fixture, not at module scope) so
    `MEETSTREAM_API_KEY` is guaranteed to already be set in the environment
    before `app.config.get_settings()` is first evaluated.
    """
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
