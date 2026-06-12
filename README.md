# AI Career Assistant

![CI](https://github.com/tiagorcfortunato/ai-career-assistant/actions/workflows/ci.yml/badge.svg)

A production-deployed **Retrieval-Augmented Generation (RAG)** career chatbot. Recruiters and hiring managers can ask natural-language questions about Tiago Fortunato's experience, projects, and skills, and receive accurate, sourced answers in real time with streaming responses.

> **Live demo:** [rag-pdf-chatbot-0w9z.onrender.com](https://rag-pdf-chatbot-0w9z.onrender.com). The previous `chatbot.tifortunato.com` AWS deployment was intentionally shut down to avoid surprise billing.

---

## Features

- **LangGraph orchestration** — query pipeline modelled as a typed `StateGraph` with conditional edges; streaming comes for free via `astream_events`
- **Hybrid retrieval** — combines semantic search (ChromaDB embeddings) with keyword search (BM25), fused via Reciprocal Rank Fusion (RRF) for best-of-both-worlds matching
- **Cross-encoder reranking with confidence gate** — `jinaai/jina-reranker-v2-base-multilingual` jointly scores `(query, chunk)` pairs; sigmoid-normalised score feeds a `max_score < 0.3 → fallback` gate. Feature-flagged (disabled on Render Free due to RAM budget; code tested end-to-end)
- **Streaming SSE responses** — token-by-token output via Server-Sent Events for a ChatGPT-like experience
- **Section-aware chunking** — for PDFs, detects headings by font-size analysis (PyMuPDF); for Markdown, splits by ATX headings
- **Conversation history** — follow-up questions resolve references via short-query history enrichment
- **Source attribution** — every answer shows which sections informed the response
- **Layered LLM** — Llama 3.3 70B primary via Groq, Llama 3.1 8B fallback on rate-limits (auto-recovery inside the graph node)
- **RAGAS evaluation pipeline** — automated quality metrics (faithfulness, relevancy, context precision/recall) using Gemini as judge
- **Cost-controlled deployment** — Render Free + Docker + managed HTTPS; reranker disabled in production to stay inside the 512MB memory limit
- **AWS infrastructure learning pass** — previously deployed manually on EC2 with Docker, Nginx, Let's Encrypt, DNS, and custom domain, then decommissioned to avoid billing risk

---

## Architecture

```
Knowledge base (Markdown)
    ↓
Section-aware chunking (ATX headings)
    ↓
Local embeddings (BAAI/bge-small-en-v1.5 via fastembed, ONNX)
    ↓
ChromaDB (local vector store inside the container/runtime path)

─────────────────────────────────────────

User question
    ↓
LangGraph StateGraph:
  1. enrich_query       ── prepend history to short follow-up queries
  2. route_query        ── keyword-scope retrieval to project files when possible
  3. retrieve           ── Hybrid search:
                           ├── Semantic (ChromaDB, top-k*2 = 40)
                           └── BM25 keyword (top-k*2 = 40)
                                ↓
                           Reciprocal Rank Fusion → top-20 candidates
  4. rerank             ── Jina cross-encoder v2 multilingual
                           scores (query, chunk) jointly → top-5
                           (feature-flagged; skipped on Render Free)
  5. evaluate_retrieval ── max_rerank_score ≥ 0.3 → high, else low
       ↓
   ┌── confidence ──┐
   ↓ high           ↓ low
  format_context    fallback_response (deterministic, no LLM call)
   ↓                  ↓
  generate_answer     END
   ↓  Groq LLM — primary: llama-3.3-70b-versatile (temperature=0)
   ↓           fallback on 429: llama-3.1-8b-instant
  generate_followups  (8B model, best-effort, fails silently)
   ↓
  END

Streaming SSE tokens emitted from generate_answer → frontend via astream_events
```

---

## Tech stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI + Pydantic |
| **LLM — primary** | Llama 3.3 70B Versatile via [Groq](https://groq.com) |
| **LLM — fallback** | Llama 3.1 8B Instant (auto on 429 rate-limit; also powers follow-up-question generation) |
| **Embeddings** | `BAAI/bge-small-en-v1.5` via `fastembed` (ONNX, runs locally) |
| **Reranker** | `jinaai/jina-reranker-v2-base-multilingual` via `fastembed` (ONNX, feature-flagged) |
| **Vector DB** | ChromaDB |
| **Keyword search** | BM25 via `rank_bm25` |
| **Orchestration** | LangGraph `StateGraph` on top of LangChain primitives |
| **Streaming** | Server-Sent Events (SSE) via `astream_events` |
| **Frontend** | Vanilla HTML/CSS/JS + marked.js |
| **Evaluation** | RAGAS with Gemini 2.5 Flash as judge |
| **Deployment** | Docker, Render Free |
| **CD** | Render auto-deploy from GitHub `main` |

---

## Getting started

### Prerequisites

- Docker and Docker Compose
- A free [Groq API key](https://console.groq.com)

### Setup

```bash
git clone https://github.com/tiagorcfortunato/ai-career-assistant.git
cd ai-career-assistant

cp .env.example .env
# Edit .env and set your GROQ_API_KEY
```

### Run

```bash
docker-compose up --build
```

- **Chat UI:** `http://localhost:8000`
- **API docs:** `http://localhost:8000/docs`

The first build downloads the embedding model (~80MB). On startup, the app indexes the curated markdown knowledge base if needed.

### Low-cost cloud deployment

For portfolio use without AWS billing risk, deploy the Docker service to Render's free web service plan using `render.yaml`.

Required environment variables:

```bash
GROQ_API_KEY=your_groq_key
RAG_RERANK_ENABLED=false
CHROMA_PATH=/tmp/chroma_db
LLM_MODEL=llama-3.1-8b-instant
```

Do not add secrets to Git. Add `GROQ_API_KEY` only in the provider dashboard. Use the generated provider URL first; configure a custom domain only after the app is working.

---

## API reference

### Query (non-streaming)

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What projects has Tiago built?",
    "history": []
  }'
```

```json
{
  "answer": "Tiago has built three main projects...",
  "sources": [
    {
      "content": "chunk preview...",
      "page": 1,
      "section": "Projects Overview",
      "document_id": "..."
    }
  ]
}
```

### Query (streaming SSE)

```bash
curl -N -X POST http://localhost:8000/api/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "Tell me about yourself", "history": []}'
```

Response is a stream of SSE events:

```
data: {"sources": [...]}

data: {"token": "Tiago"}
data: {"token": " is"}
...
data: [DONE]
```

### Upload a PDF

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@document.pdf"
```

---

## Project structure

```
app/
├── api/
│   └── routes.py              # Upload, query, stream endpoints
├── services/
│   ├── ingestion.py           # PDF/MD → section-aware chunks → ChromaDB
│   ├── retrieval.py           # Hybrid search (semantic + BM25 + RRF) → LLM
│   └── embeddings.py          # FastEmbeddings wrapper
├── models/
│   └── schemas.py             # Pydantic request/response models
├── static/
│   └── index.html             # Chat UI with markdown rendering
├── config.py                  # Pydantic settings from env
└── main.py                    # FastAPI app + lifespan startup

data/
└── knowledge_base.md          # Career knowledge base

tests/                         # Pytest tests for upload, query, health
eval_ragas.py                  # RAGAS evaluation pipeline
Dockerfile                     # Docker runtime for the FastAPI app
```

---

## Evaluation

Run RAGAS evaluation against the live deployment:

```bash
GOOGLE_API_KEY=your_gemini_key python eval_ragas.py
```

Metrics evaluated:
- **Faithfulness** — Are factual claims grounded in retrieved context?
- **Answer Relevancy** — Does the answer address the question?
- **Context Precision** — Are retrieved chunks relevant?
- **Context Recall** — Were the right chunks retrieved?

Gemini 2.5 Flash is used as the evaluator LLM (different from the chatbot's Groq model — best practice for unbiased evaluation).

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | required | Your Groq API key (free at console.groq.com) |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Primary Groq model. 8B fallback is hard-coded in `retrieval.py` for 429 recovery + follow-up generation. |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model (fastembed, ONNX) |
| `CHROMA_PATH` | `./chroma_db` | ChromaDB persistence directory. On Render Free, use `/tmp/chroma_db`. |
| `CHUNK_SIZE` | `500` | Max characters per chunk |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |
| `RETRIEVAL_K` | `20` | RRF candidate pool size (reranker then narrows to `RAG_RERANK_TOP_K`) |
| `RAG_RERANK_MODEL` | `jinaai/jina-reranker-v2-base-multilingual` | Cross-encoder checkpoint used when reranker is enabled |
| `RAG_RERANK_TOP_K` | `5` | Post-rerank cut — how many chunks reach the LLM |
| `RAG_RERANK_MIN_SCORE` | `0.3` | Sigmoid-normalised confidence-gate threshold |
| `RAG_RERANK_ENABLED` | `true` (code) / `false` (prod) | Feature flag — off on Render Free due to the 350 MB Jina ONNX footprint |
| `GOOGLE_API_KEY` | optional | For RAGAS evaluation only (Gemini as judge) |

---

## Production deployment

The current live demo runs on Render Free as a Docker web service:

- URL: `https://rag-pdf-chatbot-0w9z.onrender.com`
- Region: Frankfurt
- Plan: Free, 512MB RAM
- HTTPS: managed by Render
- Known tradeoff: cold start after inactivity

The previous AWS EC2 deployment was built as an infrastructure learning pass and then intentionally decommissioned to avoid surprise billing.

### Render deployment

Push to `main` → Render builds and runs the Docker service.

Required environment variables:

```bash
GROQ_API_KEY=your_groq_key
RAG_RERANK_ENABLED=false
CHROMA_PATH=/tmp/chroma_db
LLM_MODEL=llama-3.1-8b-instant
```

`RAG_RERANK_ENABLED=false` is important on the free instance. The reranker is implemented and tested, but loading the Jina ONNX model can push the service over Render's 512MB limit.

### Readiness semantics

`/health` returns 503 during lifespan startup, then 200 once the app is ready. Render uses this path to verify the service.

### Previous AWS learning deployment

The project was also deployed manually on AWS EC2 with Docker, Nginx, Let's Encrypt, DNS, and a custom domain. That setup proved production infrastructure skills, but it is not the current live deployment because the goal now is a zero-surprise-cost portfolio demo.
