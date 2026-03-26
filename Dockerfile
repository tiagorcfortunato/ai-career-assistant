FROM python:3.11-slim

WORKDIR /app

# Install build tools required by some Python packages (e.g. fastembed)
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create directories for volumes
RUN mkdir -p data chroma_db

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
