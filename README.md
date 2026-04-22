# AI Career Assistant

![CI](https://github.com/tiagorcfortunato/ai-career-assistant/actions/workflows/ci.yml/badge.svg)

A production-deployed **Retrieval-Augmented Generation (RAG)** career chatbot. Recruiters and hiring managers can ask natural-language questions about Tiago Fortunato's experience, projects, and skills, and receive accurate, sourced answers in real time with streaming responses.

> **Live demo:** [https://chatbot.tifortunato.com](https://chatbot.tifortunato.com)

---

## Features

- **LangGraph orchestration** — query pipeline modelled as a typed `StateGraph` with conditional edges; streaming comes for free via `astream_events`
- **Hybrid retrieval** — combines semantic search (ChromaDB embeddings) with keyword search (BM25), fused via Reciprocal Rank Fusion (RRF) for best-of-both-worlds matching
- **Cross-encoder reranking with confidence gate** — `jinaai/jina-reranker-v2-base-multilingual` jointly scores `(query, chunk)` pairs; sigmoid-normalised score feeds a `max_score < 0.3 → fallback` gate. Feature-flagged (disabled in prod on t3.micro due to RAM budget; code tested end-to-end)
- **Streaming SSE responses** — token-by-token output via Server-Sent Events for a ChatGPT-like experience
- **Section-aware chunking** — for PDFs, detects headings by font-size analysis (PyMuPDF); for Markdown, splits by ATX headings
- **Conversation history** — follow-up questions resolve references via short-query history enrichment
- **Source attribution** — every answer shows which sections informed the response
- **Layered LLM** — Llama 3.3 70B primary via Groq, Llama 3.1 8B fallback on rate-limits (auto-recovery inside the graph node)
- **RAGAS evaluation pipeline** — automated quality metrics (faithfulness, relevancy, context precision/recall) using Gemini as judge
- **CD pipeline** — push-to-main triggers GitHub Actions → GHCR image build → SSH deploy to EC2 with readiness-gated healthcheck + smoke test + auto-rollback on failure
- **Persistent host volumes** — ChromaDB index and fastembed model cache live on the EC2 host, survive container replacement, keep deploys ~5s instead of re-ingesting every time
- **Production deployment** — AWS EC2 + Docker + Nginx + Let's Encrypt HTTPS + custom domain

---

## Architecture

```
Knowledge base (Markdown)
    ↓
Section-aware chunking (ATX headings)
    ↓
Local embeddings (BAAI/bge-small-en-v1.5 via fastembed, ONNX)
    ↓
ChromaDB (persistent, mounted from host volume into the container)

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
                           (feature-flagged; skipped in prod on t3.micro)
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
| **Vector DB** | ChromaDB (persistent, host-volume mounted) |
| **Keyword search** | BM25 via `rank_bm25` |
| **Orchestration** | LangGraph `StateGraph` on top of LangChain primitives |
| **Streaming** | Server-Sent Events (SSE) via `astream_events` |
| **Frontend** | Vanilla HTML/CSS/JS + marked.js |
| **Evaluation** | RAGAS with Gemini 2.5 Flash as judge |
| **Deployment** | Docker, AWS EC2 (t3.micro), Nginx, Let's Encrypt |
| **CD** | GitHub Actions → GHCR → EC2 pull (readiness-gated, auto-rollback) |

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

The first build downloads the embedding model (~80MB) and pre-ingests the knowledge base. Subsequent starts are instant.

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
└── knowledge_base.md          # Career knowledge base (pre-ingested)

tests/                         # Pytest tests for upload, query, health
eval_ragas.py                  # RAGAS evaluation pipeline
Dockerfile                     # Pre-ingests KB at build time
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
| `CHROMA_PATH` | `./chroma_db` | ChromaDB persistence directory (container mounts a host volume here in prod) |
| `CHUNK_SIZE` | `500` | Max characters per chunk |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |
| `RETRIEVAL_K` | `20` | RRF candidate pool size (reranker then narrows to `RAG_RERANK_TOP_K`) |
| `RAG_RERANK_MODEL` | `jinaai/jina-reranker-v2-base-multilingual` | Cross-encoder checkpoint used when reranker is enabled |
| `RAG_RERANK_TOP_K` | `5` | Post-rerank cut — how many chunks reach the LLM |
| `RAG_RERANK_MIN_SCORE` | `0.3` | Sigmoid-normalised confidence-gate threshold |
| `RAG_RERANK_ENABLED` | `true` (code) / `false` (prod) | Feature flag — off in prod on t3.micro due to 350 MB Jina ONNX footprint |
| `GOOGLE_API_KEY` | optional | For RAGAS evaluation only (Gemini as judge) |

---

## Production deployment

The live demo runs on AWS EC2 (t3.micro, eu-central-1, 1 GB RAM) behind Nginx with Let's Encrypt TLS on a custom Namecheap domain.

### CD pipeline

Push to `main` → GitHub Actions runs three jobs:

1. **`test`** — pytest on the runner
2. **`build-and-push`** — Docker image built off-box on the GH runner (4 GB RAM, avoids t3.micro OOM), pushed to GHCR as `ghcr.io/<owner>/<repo>:sha-<short>`
3. **`deploy`** — SSH to EC2, `docker pull` the pre-built image, stop old container, start new one with host-volume mounts + `--memory=800m`. Poll `/health` up to 120 s, then a live `POST /api/query` smoke test. Any failure → auto-rollback to the previous image by SHA. See `DEPLOYMENT.md` for the full runbook.

### Host volumes (survive deploys)

- `chroma_db` → `/app/chroma_db` (~3 MB, pre-ingested via the separate `bootstrap-chroma.yml` workflow)
- fastembed model cache → `/root/.cache/fastembed` (embedder + reranker ONNX weights; lazy-downloads on miss)

The result: normal deploys are ~5 s container swaps, not re-ingestion runs. The bootstrap workflow only re-runs when a knowledge-base markdown file changes.

### Readiness semantics

`/health` returns 503 during lifespan startup (ingestion check + warmup), 200 once ready. The deploy workflow polls for 200 before calling the smoke test — no more racing against a not-yet-ready container.

### Runtime hardening

- `--restart unless-stopped` for crash recovery
- `--memory=800m --memory-swap=1600m` to bound the container below the host budget
- `127.0.0.1:8000` bind — Nginx is the only public surface
- Let's Encrypt auto-renewal via cron
