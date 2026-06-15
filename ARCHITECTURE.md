# Architecture

## Overview

This repository contains Tiago Fortunato's AI Career Assistant: a Retrieval-Augmented Generation chatbot for recruiters, hiring managers, and technical interviewers. It answers questions about Tiago's experience, projects, skills, and motivations using curated knowledge bases, with streamed responses and source attribution.

Live URL: [https://rag-pdf-chatbot-0w9z.onrender.com](https://rag-pdf-chatbot-0w9z.onrender.com)

The FastAPI app serves both the JSON/SSE API and the static chat UI. The main user flow is `POST /api/query/stream`, which streams Server-Sent Events to the frontend. A non-streaming `POST /api/query` endpoint uses the same graph pipeline and returns a full JSON response.

## Tech Stack

- FastAPI for the HTTP API, health check, CORS, static file serving, and request validation through Pydantic models.
- LangChain and LangGraph for LLM calls, prompt composition, message history handling, and the query pipeline `StateGraph`.
- ChromaDB as the persisted local vector store.
- `fastembed` with `BAAI/bge-small-en-v1.5` for local CPU embeddings.
- `rank_bm25` for keyword retrieval.
- Optional `fastembed` cross-encoder reranking with `jinaai/jina-reranker-v2-base-multilingual`.
- Groq for chat completion calls. The code default primary model is `llama-3.3-70b-versatile`; production Render config sets `LLM_MODEL=llama-3.1-8b-instant`. The fallback model on rate limits is `llama-3.1-8b-instant`.
- Docker for the runtime image.
- Render Free for the current public deployment.

## Retrieval Pipeline

The query pipeline is compiled in `app/services/graph.py` as a LangGraph `StateGraph`:

1. `enrich_query`: if a user question is short and there is chat history, the search query is expanded with recent conversation context.
2. `route_query`: simple keyword routing can scope retrieval to one project knowledge file plus `knowledge_base.md`. Ambiguous or general questions search all indexed content.
3. `retrieve`: hybrid retrieval combines dense semantic search from ChromaDB with BM25 keyword search. Each side retrieves `k * 2` candidates, where `k` is `RETRIEVAL_K`.
4. Reciprocal Rank Fusion ranks the semantic and BM25 result lists together using `1 / (rank + 60)`.
5. `rerank`: when `RAG_RERANK_ENABLED=true`, the Jina v2 multilingual cross-encoder scores each `(query, chunk)` pair, stores a sigmoid-normalized `rerank_score`, and keeps `RAG_RERANK_TOP_K` chunks. When disabled, the graph uses the RRF top chunks directly.
6. `evaluate_retrieval`: when rerank is enabled, the best rerank score is compared with `RAG_RERANK_MIN_SCORE`. Empty or low-confidence retrieval routes to a deterministic fallback response instead of sending weak context to the LLM.
7. `format_context`: selected chunks are formatted with `[SOURCE: ...]` labels so the LLM can distinguish the general profile, Odys, the RAG chatbot, and the Inspection API.
8. `generate_answer`: Groq generates the answer with `temperature=0`, using retrieved context and chat history.
9. `generate_followups`: a best-effort Groq call generates three short follow-up questions.

Relevant config flags are loaded from environment variables in `app/config.py`:

- `RETRIEVAL_K` controls the RRF candidate pool size. Default in code: `20`.
- `RAG_RERANK_ENABLED` controls whether the cross-encoder loads and runs. Default in code: `true`; Render production sets it to `false`.
- `RAG_RERANK_MODEL` defaults to `jinaai/jina-reranker-v2-base-multilingual`.
- `RAG_RERANK_TOP_K` defaults to `5`.
- `RAG_RERANK_MIN_SCORE` defaults to `0.3`.

## Knowledge Bases

The app ships four curated Markdown knowledge bases under `data/`:

- Base: `data/knowledge_base.md`
- Odys: `data/odys_knowledge.md`
- RAG: `data/rag_chatbot_knowledge.md`
- Inspection: `data/inspection_api_knowledge.md`

On startup, `app/main.py` runs lifespan checks for those four files. For each file, it asks ChromaDB whether any chunk with that filename is already indexed. If the filename is present, startup skips ingestion for that file. If it is missing, `ingest_markdown()` reads the Markdown file, splits it by ATX headings, applies recursive splitting for oversized sections, embeds the chunks with `fastembed`, and stores them in ChromaDB with metadata including `document_id`, `filename`, `page`, and `section`.

The API also exposes `POST /api/upload` for PDF ingestion. Uploaded PDFs are saved under `data/`, split with PyMuPDF-based heading detection, embedded, and added to ChromaDB.

Re-ingestion is needed when a knowledge base file's content changes, when chunking settings change, when the embedding model changes, or when the ChromaDB directory is cleared. Because startup checks only whether a filename already exists in ChromaDB, editing an existing Markdown file with the same filename does not automatically replace its old chunks; the index must be regenerated or cleared so startup can ingest the updated content.

## Deployment Tradeoffs

The current live deployment uses Render Free instead of the previous AWS EC2 deployment. The README notes that the AWS deployment at `chatbot.tifortunato.com` was intentionally shut down to avoid surprise billing. Render Free provides a cost-controlled public demo with Docker and managed HTTPS.

Render Free has a 512MB memory limit. That constraint affects several production choices:

- The Docker image copies the four Markdown knowledge bases and the pre-ingested `chroma_db/` directory.
- Shipping `chroma_db/` in the image lets startup skip re-ingestion when the expected filenames are already indexed.
- Skipping startup re-ingestion reduces memory pressure during deployment and keeps `/health` readiness focused on verifying the existing index.
- Production sets `RAG_RERANK_ENABLED=false` in `render.yaml`. The reranker code and tests remain in the repository, but loading the Jina ONNX model is avoided on the free instance.

The tradeoff is that production relies on the committed ChromaDB index matching the committed knowledge base files. When the knowledge bases change, the index should be regenerated before building the production image.

## Local Development

Create a local `.env` from `.env.example` and set at least:

```bash
GROQ_API_KEY=your_key_here
```

Useful environment variables:

```bash
LLM_MODEL=llama-3.1-8b-instant
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
CHROMA_PATH=./chroma_db
CHUNK_SIZE=500
CHUNK_OVERLAP=50
RETRIEVAL_K=20
RAG_RERANK_MODEL=jinaai/jina-reranker-v2-base-multilingual
RAG_RERANK_TOP_K=5
RAG_RERANK_MIN_SCORE=0.3
RAG_RERANK_ENABLED=false
```

Run locally with:

```bash
./run_local.sh
```

`run_local.sh` requires `.env`, sets `CHROMA_PATH=./chroma_db_local`, and starts Uvicorn with hot reload on `127.0.0.1:8000`. The local UI is available at `http://localhost:8000`, and FastAPI docs are available at `http://localhost:8000/docs`.

## Known Limitations

- Render Free can cold start after inactivity.
- Cross-encoder reranking is disabled in production with `RAG_RERANK_ENABLED=false`.
- Startup ingestion skips files by filename if they already exist in ChromaDB, so changed knowledge base content requires regenerating or clearing the index.
