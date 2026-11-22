"""Shared fixtures: MeetStream's REST API is mocked at the `httpx` transport layer
with `respx`, so no test makes a network call or needs a MeetStream account."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import respx

from llama_index_meetstream.client import MeetStreamClient

API_URL = "https://api.meetstream.test/api/v1"


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch):
    monkeypatch.setattr("llama_index_meetstream.client._RETRY_BASE_DELAY_SECONDS", 0)


@pytest.fixture
def api_mock() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=API_URL, assert_all_called=False) as router:
        yield router


@pytest.fixture
def client() -> MeetStreamClient:
    return MeetStreamClient(api_key="ms_test_key", base_url=API_URL)
