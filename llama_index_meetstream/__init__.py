"""llama-index-meetstream: native LlamaIndex integration for MeetStream.

Public API:
    - `MeetStreamClient` -- talks to the MeetStream bridge server.
    - `MeetStreamReader` -- loads a meeting transcript as LlamaIndex `Document`s.
    - `llama_index_meetstream.tools.get_meetstream_tools` -- MeetStream tools for agents.

See the package README and the repository root `docs/ARCHITECTURE.md` for the
full design.
"""

from llama_index_meetstream.client import MeetStreamClient
from llama_index_meetstream.exceptions import MeetStreamAPIError, MeetStreamConnectionError, MeetStreamError
from llama_index_meetstream.readers import MeetStreamReader

__version__ = "0.1.0"

__all__ = [
    "MeetStreamAPIError",
    "MeetStreamClient",
    "MeetStreamConnectionError",
    "MeetStreamError",
    "MeetStreamReader",
]
