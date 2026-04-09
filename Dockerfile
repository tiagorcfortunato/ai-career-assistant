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
COPY data/Tiago_Fortunato_Expert_System_Road_Hazard_Detection.pdf ./data/Tiago_Fortunato_Expert_System_Road_Hazard_Detection.pdf

# Pre-ingest knowledge base and thesis at build time so there's no memory spike at runtime
# GROQ_API_KEY is not used during ingestion (embeddings are local via fastembed)
RUN GROQ_API_KEY=build-placeholder python -c "\
from app.services.ingestion import ingest_markdown, ingest_pdf; \
from pathlib import Path; \
doc_id, chunks = ingest_markdown(Path('data/knowledge_base.md'), 'knowledge_base.md'); \
print(f'Pre-indexed KB: {chunks} chunks, doc_id={doc_id}'); \
doc_id2, chunks2 = ingest_pdf(Path('data/Tiago_Fortunato_Expert_System_Road_Hazard_Detection.pdf'), 'Tiago_Fortunato_Expert_System_Road_Hazard_Detection.pdf'); \
print(f'Pre-indexed thesis: {chunks2} chunks, doc_id={doc_id2}')"

RUN mkdir -p chroma_db

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
