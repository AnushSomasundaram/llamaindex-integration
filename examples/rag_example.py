"""RAG (retrieval-augmented generation) over a MeetStream meeting transcript.

Pipeline:

    MeetStream
        |
    MeetStreamReader   (this package -- bridge-backed transcript segments)
        |
    LlamaIndex Documents
        |
    VectorStoreIndex
        |
    Query Engine

`VectorStoreIndex.from_documents` here uses LlamaIndex's default in-memory
vector store -- only an example choice, requiring no extra vector-database
dependency. The `Document` objects `MeetStreamReader` produces are plain
LlamaIndex `Document`s and work with any LlamaIndex-compatible vector store
(Chroma, Pinecone, pgvector, ...) -- swap the storage context for whichever
your application already uses.

Prerequisites:
    1. The bridge server running, pointed at a real MeetStream API key.
    2. `pip install -e ".[examples]"` from this package's directory.
    3. `OPENAI_API_KEY` set (this example uses OpenAI for embeddings + the
       LLM; swap `OpenAIEmbedding`/`OpenAI` for any other LlamaIndex
       embedding/LLM integration if you'd rather not use OpenAI).
    4. `MEETSTREAM_API_KEY` / `MEETSTREAM_BRIDGE_URL` set, or passed explicitly.

Run: `python examples/rag_example.py <meeting_id> "What deadline was discussed?"`
"""

from __future__ import annotations

import sys

from llama_index.core import Settings, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

from llama_index_meetstream import MeetStreamReader


def main() -> None:
    if len(sys.argv) != 3:
        print(f'Usage: python {sys.argv[0]} <meeting_id> "<question>"')
        raise SystemExit(1)
    meeting_id, question = sys.argv[1], sys.argv[2]

    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    Settings.llm = OpenAI(model="gpt-4o-mini")

    documents = MeetStreamReader(meeting_id=meeting_id).load_data()
    if not documents:
        print(f"No transcript segments found for meeting {meeting_id}.")
        return

    # Transcript segments from MeetStream are already speaker-turn-sized
    # chunks (see docs/ARCHITECTURE.md §7); `VectorStoreIndex.from_documents`
    # will still run its default `SentenceSplitter` over them, which is a
    # no-op for segments already shorter than the default chunk size and
    # only splits the rare unusually-long segment.
    index = VectorStoreIndex.from_documents(documents)
    query_engine = index.as_query_engine(similarity_top_k=4)

    response = query_engine.query(question)
    print(response)


if __name__ == "__main__":
    main()
