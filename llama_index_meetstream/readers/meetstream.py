"""`MeetStreamReader` -- turns a MeetStream meeting transcript into LlamaIndex
`Document` objects.

Layer: this is where `llama_index_meetstream` translates the bridge's
normalized transcript response into framework-native objects. Mirrors
`langchain_meetstream.document_loaders.meetstream.MeetStreamLoader` exactly
in behavior (same one-`Document`-per-segment design, same metadata fields) --
see that module's docstring for the full "why" behind those choices, which
applies here unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document

from llama_index_meetstream.client import MeetStreamClient
from llama_index_meetstream.exceptions import MeetStreamAPIError

logger = logging.getLogger(__name__)


class MeetStreamReader(BaseReader):
    """Loads a MeetStream meeting transcript as LlamaIndex `Document`s.

    Example:
        ```python
        from llama_index_meetstream import MeetStreamReader

        reader = MeetStreamReader(meeting_id="meeting_123", api_key="...")
        documents = reader.load_data()
        ```

    One `Document` per transcript segment (speaker turn) -- see
    `langchain_meetstream`'s equivalent loader for the full rationale, which
    applies identically here: it preserves per-segment `speaker`/
    `start_time`/`end_time` metadata for retrieval, and defers any further
    chunking to LlamaIndex's own node parsers/splitters (see
    `examples/rag_example.py`) rather than pre-chunking in this reader or the
    bridge.
    """

    def __init__(
        self,
        meeting_id: str,
        api_key: str | None = None,
        base_url: str | None = None,
        client: MeetStreamClient | None = None,
    ) -> None:
        """
        Args:
            meeting_id: The MeetStream meeting/bot id to load a transcript for.
            api_key: Passed through to `MeetStreamClient` if `client` isn't given.
            base_url: Passed through to `MeetStreamClient` if `client` isn't given.
            client: An existing `MeetStreamClient` to reuse instead of
                constructing a new one from `api_key`/`base_url`.
        """
        self.meeting_id = meeting_id
        self._client = client or MeetStreamClient(api_key=api_key, base_url=base_url)

    def lazy_load_data(self, *args: object, **load_kwargs: object) -> Iterable[Document]:
        """Yields one `Document` per transcript segment.

        Implementing `lazy_load_data` (rather than `load_data` directly) is
        the currently recommended `BaseReader` pattern -- `load_data()`/
        `aload_data()` are provided for free by the base class (see
        `docs/ARCHITECTURE.md` §11 and §13 for the version this was verified
        against). `*args`/`**load_kwargs` are unused -- this reader is
        parameterized entirely through `__init__` (`meeting_id`), matching
        the constructor-configured style shown in this project's spec, rather
        than `BaseReader`'s more general per-call-arguments style meant for
        readers that load different things on each call.
        """
        transcript = self._client.get_transcript(self.meeting_id)

        title: str | None = None
        platform: str | None = None
        try:
            meeting = self._client.get_meeting(self.meeting_id)
            title = meeting.title
            platform = meeting.platform
        except MeetStreamAPIError as exc:
            logger.warning("Could not fetch meeting metadata for %s: %s", self.meeting_id, exc)

        for segment in transcript.segments:
            yield Document(
                text=segment.text,
                metadata={
                    "source": "meetstream",
                    "meeting_id": self.meeting_id,
                    "meeting_title": title,
                    "platform": platform,
                    "speaker": segment.speaker,
                    "start_time": segment.start_time,
                    "end_time": segment.end_time,
                },
            )
