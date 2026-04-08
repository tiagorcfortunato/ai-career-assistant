from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str
    llm_model: str = "llama-3.1-8b-instant"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    chroma_path: str = "./chroma_db"
    chunk_size: int = 500
    chunk_overlap: int = 50
    retrieval_k: int = 6

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
