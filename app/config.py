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
    llm_model: str = "llama-3.1-8b-instant"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    chroma_path: str = "./chroma_db"
    chunk_size: int = 500
    chunk_overlap: int = 50
    retrieval_k: int = 8

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
