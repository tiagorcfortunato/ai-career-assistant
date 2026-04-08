FROM python:3.11-slim

WORKDIR /app

# Install build tools required by some Python packages (e.g. fastembed)
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and tests
COPY app/ ./app/
COPY tests/ ./tests/

COPY data/knowledge_base.md ./data/knowledge_base.md

# Pre-ingest knowledge base at build time so there's no memory spike at runtime
# GROQ_API_KEY is not used during ingestion (embeddings are local via fastembed)
RUN GROQ_API_KEY=build-placeholder python -c "\
from app.services.ingestion import ingest_markdown; \
from pathlib import Path; \
doc_id, chunks = ingest_markdown(Path('data/knowledge_base.md'), 'knowledge_base.md'); \
print(f'Pre-indexed: {chunks} chunks, doc_id={doc_id}')"

RUN mkdir -p chroma_db

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
