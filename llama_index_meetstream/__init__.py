"""llama-index-meetstream: native LlamaIndex integration for MeetStream.

Public API:
    - `MeetStreamClient` -- calls MeetStream's REST API.
    - `MeetStreamReader` -- loads a meeting transcript as LlamaIndex `Document`s.
    - `llama_index_meetstream.tools.get_meetstream_tools` -- MeetStream tools for agents.

See the README and `docs/ARCHITECTURE.md` for the design.
"""

from llama_index_meetstream.client import DEFAULT_TRANSCRIPTION_PROVIDER, TRANSCRIPTION_PROVIDERS, MeetStreamClient
from llama_index_meetstream.exceptions import MeetStreamAPIError, MeetStreamConnectionError, MeetStreamError
from llama_index_meetstream.readers import MeetStreamReader

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_TRANSCRIPTION_PROVIDER",
    "TRANSCRIPTION_PROVIDERS",
    "MeetStreamAPIError",
    "MeetStreamClient",
    "MeetStreamConnectionError",
    "MeetStreamError",
    "MeetStreamReader",
]
