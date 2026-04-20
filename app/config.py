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
    retrieval_k: int = 10

    # Low-confidence retrieval thresholds, consumed by evaluate_retrieval_node.
    # Low-confidence → bypass LLM and return a deterministic fallback answer
    # instead of risking hallucination on weak chunks.
    rag_threshold_hi: float = 0.3
    rag_threshold_mid: float = 0.5
    rag_min_chunks: int = 2

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
