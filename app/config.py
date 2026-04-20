"""
app/config.py — Application Configuration

Loads settings from environment variables (or .env file) using pydantic-settings.
This keeps secrets (like GROQ_API_KEY) out of the code and makes the app
configurable without code changes.

Key settings:
  groq_api_key    → API key for Groq LLM (Llama 3.1 8B Instant)
  llm_model       → Which LLM to use (default: llama-3.1-8b-instant)
  embedding_model → Which embedding model (default: BAAI/bge-small-en-v1.5)
  chroma_path     → Where ChromaDB stores its data on disk
  chunk_size      → Target size for text chunks (500 chars)
  chunk_overlap   → Overlap between chunks (50 chars)
  retrieval_k     → Number of chunks to retrieve per query (10)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str
    llm_model: str = "llama-3.3-70b-versatile"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    chroma_path: str = "./chroma_db"
    chunk_size: int = 1000
    chunk_overlap: int = 100

    # Size of the RRF candidate pool handed to the reranker. Bumped from 10 to
    # 20 because rerank quality improves with a richer candidate set — the
    # cross-encoder narrows this back down to rag_rerank_top_k for the LLM.
    retrieval_k: int = 20

    # Cross-encoder rerank settings (see graph.py :: rerank_node and
    # retrieval.py :: _rerank_chunks). The rerank score is the primary
    # relevance gate — RRF scores are kept on chunks for debugging only.
    #
    # Default is the multilingual Jina reranker, not ms-marco-MiniLM, because
    # production traffic to this chatbot mixes English and German and the
    # English-only MS MARCO checkpoint scored on-topic German queries at
    # sigmoid ~0.12 (well below 0.3) during smoke testing. Same ONNX/fastembed
    # pipeline, just a multilingual checkpoint.
    rag_rerank_model: str = "jinaai/jina-reranker-v2-base-multilingual"
    rag_rerank_top_k: int = 5
    rag_rerank_min_score: float = 0.3  # sigmoid-normalised; tune per model

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
