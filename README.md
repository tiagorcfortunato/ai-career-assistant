# RAG PDF Chatbot

A production-ready **Retrieval-Augmented Generation (RAG)** application that lets you upload PDFs and have a contextual conversation about their content.

Upload multiple documents, ask questions, and get accurate answers grounded in your files — with source attribution showing exactly which section each answer came from.

> **Live demo:** [https://rag-pdf-chatbot-0w9z.onrender.com](https://rag-pdf-chatbot-0w9z.onrender.com)

---

## Features

- **Multi-document support** — upload multiple PDFs and query them individually or all at once
- **Conversation history** — follow-up questions work naturally ("tell me more about the first one")
- **Section-aware chunking** — detects document headings by font size to keep related content together
- **Source attribution** — every answer shows which section and page it came from
- **Chat interface** — clean browser UI, no Postman required
- **REST API** — fully documented at `/docs` (OpenAPI/Swagger)

---

## How it works

```
PDF upload
    ↓
Font-size analysis → heading detection → section-aware chunks
    ↓
Local embeddings (BAAI/bge-small-en-v1.5 via fastembed)
    ↓
ChromaDB (persistent vector store)

─────────────────────────────────────────

User question
    ↓
Embed question → similarity search → top-6 most relevant chunks
    ↓
Prompt: system instructions + conversation history + context + question
    ↓
Groq LLM (llama-3.1-8b-instant)
    ↓
Answer + sources
```

---

## Tech stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI |
| **LLM** | Llama 3.1 8B via [Groq](https://groq.com) |
| **Embeddings** | `BAAI/bge-small-en-v1.5` (fastembed, runs locally) |
| **Vector DB** | ChromaDB (persistent) |
| **Orchestration** | LangChain |
| **Frontend** | Vanilla HTML/CSS/JS served by FastAPI |
| **Deployment** | Docker / Docker Compose |

---

## Getting started

### Prerequisites

- Docker and Docker Compose
- A free [Groq API key](https://console.groq.com)

### Setup

```bash
git clone https://github.com/tiagorcfortunato/rag-pdf-chatbot.git
cd rag-pdf-chatbot

cp .env.example .env
# Edit .env and set your GROQ_API_KEY
```

### Run

```bash
docker-compose up --build
```

- **Chat UI:** `http://localhost:8000`
- **API docs:** `http://localhost:8000/docs`

First run downloads the embedding model (~80MB). Subsequent starts are instant.

---

## API reference

### Upload a PDF

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@document.pdf"
```

```json
{
  "document_id": "a1b2c3d4-...",
  "filename": "document.pdf",
  "chunks_count": 18
}
```

### Ask a question

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the main topics covered?",
    "document_id": "a1b2c3d4-...",
    "history": []
  }'
```

```json
{
  "answer": "The document covers...",
  "sources": [
    {
      "content": "chunk preview...",
      "page": 2,
      "section": "Introduction",
      "document_id": "a1b2c3d4-..."
    }
  ]
}
```

### List documents

```bash
curl http://localhost:8000/api/documents
```

---

## Project structure

```
app/
├── api/
│   └── routes.py          # Upload, query, list endpoints
├── services/
│   ├── ingestion.py        # PDF → section-aware chunks → ChromaDB
│   ├── retrieval.py        # question + history → search → LLM → answer
│   └── embeddings.py       # FastEmbeddings wrapper (fastembed)
├── models/
│   └── schemas.py          # Pydantic request/response models
├── static/
│   └── index.html          # Chat UI
├── config.py               # Settings loaded from .env
└── main.py                 # FastAPI app + static file serving
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | required | Your Groq API key (free at console.groq.com) |
| `LLM_MODEL` | `llama-3.1-8b-instant` | Groq model to use |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model |
| `CHROMA_PATH` | `./chroma_db` | ChromaDB persistence directory |
| `CHUNK_SIZE` | `500` | Max characters per chunk (fallback for large sections) |
| `CHUNK_OVERLAP` | `50` | Overlap between fallback chunks |
| `RETRIEVAL_K` | `6` | Number of chunks retrieved per query |
