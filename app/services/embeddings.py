"""
app/services/embeddings.py — Local Embedding Model (the "translator")

Converts text into numerical vectors (arrays of 384 numbers) so the computer
can measure how similar two pieces of text are using cosine similarity.

Uses BAAI/bge-small-en-v1.5 via fastembed — a local model (~80MB) that runs on CPU.
No API calls, no cost, no network dependency.

Why local instead of OpenAI API:
  - Zero cost per query (vs $0.02/1M tokens for OpenAI ada-002)
  - No latency from network calls (~1ms local vs ~200ms API)
  - Works offline
  - Trade-off: slightly lower quality than larger models, but sufficient for 500-char chunks

This class wraps fastembed's TextEmbedding to implement LangChain's Embeddings interface,
so it plugs directly into LangChain's Chroma integration.
"""

from fastembed import TextEmbedding
from langchain_core.embeddings import Embeddings


class FastEmbeddings(Embeddings):
    """Thin wrapper around fastembed that implements the LangChain Embeddings interface."""

    def __init__(self, model_name: str):
        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [embedding.tolist() for embedding in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return list(self._model.embed([text]))[0].tolist()
