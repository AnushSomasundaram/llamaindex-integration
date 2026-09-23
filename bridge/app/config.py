"""Bridge server configuration.

Centralizing settings here (rather than reading `os.environ` scattered across
`api/`, `services/`, and `clients/`) means there is exactly one place that
knows the environment variable names, and exactly one place a test needs to
monkeypatch to control bridge behavior end to end.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the bridge, sourced from environment variables.

    `meetstream_api_key` has no default: the bridge cannot make a single real
    MeetStream call without it, so failing fast at startup (rather than at the
    first request) is the more honest behavior.
    """

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    meetstream_api_key: str
    meetstream_base_url: str = "https://api.meetstream.ai/api/v1"

    # Applied to every outbound call to the real MeetStream API. MeetStream's
    # own server has been observed (see docs/ARCHITECTURE.md §3) to return a
    # transient 503 under load; this timeout is about *this bridge* giving up
    # on a hung connection, independent of the client's own retry policy.
    meetstream_request_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    """Returns the process-wide `Settings` singleton.

    `lru_cache` (rather than a module-level global) makes this trivially
    overridable in tests via `get_settings.cache_clear()` plus environment
    patching, without needing a separate test-only settings factory.
    """
    return Settings()  # type: ignore[call-arg]
