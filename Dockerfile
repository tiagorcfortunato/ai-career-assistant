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
COPY data/odys_knowledge.md ./data/odys_knowledge.md
COPY data/rag_chatbot_knowledge.md ./data/rag_chatbot_knowledge.md
COPY data/inspection_api_knowledge.md ./data/inspection_api_knowledge.md

# Pre-ingest knowledge bases at build time so there's no memory spike at runtime
RUN GROQ_API_KEY=build-placeholder python -c "\
from app.services.ingestion import ingest_markdown; \
from pathlib import Path; \
doc_id, chunks = ingest_markdown(Path('data/knowledge_base.md'), 'knowledge_base.md'); \
print(f'Pre-indexed KB: {chunks} chunks, doc_id={doc_id}'); \
doc_id2, chunks2 = ingest_markdown(Path('data/odys_knowledge.md'), 'odys_knowledge.md'); \
print(f'Pre-indexed Odys: {chunks2} chunks, doc_id={doc_id2}'); \
doc_id3, chunks3 = ingest_markdown(Path('data/rag_chatbot_knowledge.md'), 'rag_chatbot_knowledge.md'); \
print(f'Pre-indexed RAG: {chunks3} chunks, doc_id={doc_id3}'); \
doc_id4, chunks4 = ingest_markdown(Path('data/inspection_api_knowledge.md'), 'inspection_api_knowledge.md'); \
print(f'Pre-indexed Inspection: {chunks4} chunks, doc_id={doc_id4}')"

RUN mkdir -p chroma_db

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
