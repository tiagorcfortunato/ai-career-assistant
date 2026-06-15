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

# Ship the pre-ingested ChromaDB inside the image so startup can skip
# re-ingestion — keeps memory usage under Render Free's 512MB cap.
# Re-generate locally by running the ingestion script, then commit chroma_db/.
COPY chroma_db/ ./chroma_db/

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
