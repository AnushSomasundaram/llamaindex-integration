"""Shared fixtures: every test mocks the bridge at the `httpx` transport layer
with `respx` -- none make a real network call and none require a running
bridge process.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import respx

BRIDGE_URL = "http://test-bridge"


@pytest.fixture
def bridge_mock() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BRIDGE_URL, assert_all_called=False) as router:
        yield router
