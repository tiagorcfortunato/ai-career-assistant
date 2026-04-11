# AI Career Assistant — RAG Chatbot Technical Deep Dive

> Technical knowledge base for the RAG Career Chatbot, Tiago Fortunato's production-deployed AI application built as a Retrieval-Augmented Generation system. Live at [chatbot.tifortunato.com](https://chatbot.tifortunato.com). Repository: [github.com/tiagorcfortunato/ai-career-assistant](https://github.com/tiagorcfortunato/ai-career-assistant).

---

## What It Is

The AI Career Assistant is a production-deployed Retrieval-Augmented Generation (RAG) chatbot that acts as Tiago Fortunato's interactive professional profile. Recruiters and hiring managers can ask natural-language questions about his experience, projects, and skills, and receive accurate, sourced answers in real time with streaming responses.

Originally built as a general-purpose PDF chatbot, Tiago evolved it into a career-focused product with a Product Engineer persona, streaming UI, hybrid search retrieval, and optimized deployment on memory-constrained infrastructure.

---

## Codebase Scale

- **11** Python files in `app/`
- **5** Pytest test files with **11** tests total
- **~810** lines of application code (excluding frontend and tests)
- **~630** lines in the vanilla HTML/CSS/JS chat UI (`app/static/index.html`)
- **2** knowledge base files ingested (main + Odys deep-dive)
- **Single Docker image** deployed on AWS EC2

---

## Tech Stack Versions

- **FastAPI 0.115** (Python backend framework)
- **Python 3.11** (Docker base image)
- **LangChain 0.3** + **langchain-groq 0.2** + **langchain-chroma 0.1.4** (orchestration)
- **Groq API** with **Llama 3.1 8B Instant** (LLM inference)
- **BAAI/bge-small-en-v1.5** via **fastembed 0.3.1** (local embeddings, ~80MB, 384-dim vectors)
- **ChromaDB 0.5** (persistent vector store)
- **rank_bm25 0.2.2** (pure-Python BM25 keyword search)
- **PyMuPDF 1.24** (fitz — PDF parsing with font-size analysis)
- **marked.js** (frontend markdown rendering)
- **Pydantic 2 + pydantic-settings 2.5** (config and validation)
- **Pytest 8.3** + **httpx 0.27** (testing)
- **Nginx 1.28** (reverse proxy on EC2)
- **Let's Encrypt / Certbot** (SSL)
- **Docker** + **Docker Compose**

---

## Project Structure

```
ai-career-assistant/
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py              # Upload, query, stream, list endpoints (106 lines)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── embeddings.py          # FastEmbeddings wrapper (34 lines)
│   │   ├── ingestion.py           # PDF/MD → chunks → ChromaDB (224 lines)
│   │   └── retrieval.py           # Hybrid search + RAG pipeline (303 lines)
│   ├── models/
│   │   └── schemas.py             # Pydantic request/response models
│   ├── static/
│   │   └── index.html             # Chat UI with streaming markdown (633 lines)
│   ├── config.py                  # Pydantic settings from env
│   └── main.py                    # FastAPI app + lifespan startup (110 lines)
│
├── data/
│   ├── knowledge_base.md          # Main career knowledge base
│   ├── odys_knowledge.md          # Odys SaaS technical deep dive
│   └── Tiago_Fortunato_Expert_System_Road_Hazard_Detection.pdf
│
├── tests/
│   ├── conftest.py                # Test fixtures (48 lines)
│   ├── test_health.py             # Health endpoint (3 tests)
│   ├── test_query.py              # Query + streaming (5 tests)
│   └── test_upload.py             # PDF upload (3 tests)
│
├── .github/workflows/ci.yml       # GitHub Actions CI
├── Dockerfile                     # Pre-ingests KBs at build time
├── docker-compose.yml
├── eval_ragas.py                  # RAGAS evaluation pipeline
├── requirements.txt
└── README.md
```

---

## Architecture

### Ingestion Pipeline (Build Time)

```
Knowledge base files (Markdown)
    ↓
Section-aware chunking (ATX heading detection)
    ├── If section ≤ 500 chars → keep whole
    └── If section > 500 chars → split with RecursiveCharacterTextSplitter
          (chunk_size=500, overlap=50), prefix each sub-chunk with section title
    ↓
Local embeddings via fastembed (BAAI/bge-small-en-v1.5)
    ↓
ChromaDB (persistent storage at ./chroma_db)
```

**Key design decision:** Ingestion happens at **Docker build time**, not runtime. The vector store is baked into the image. This avoids the memory spike of loading fastembed + ChromaDB + ingesting chunks all at once on startup — critical for fitting within the t3.micro's 1GB RAM.

### Query Pipeline (Runtime)

```
User question (via chat UI or POST /api/query or POST /api/query/stream)
    ↓
History enrichment (if query has <5 words AND history exists)
    ├── Prepend last 2 conversation exchanges to search query
    └── Resolves references like "tell me more about the first one"
    ↓
Hybrid Search (dual retrieval)
    ├── Semantic search: vector_store.similarity_search(k=k*2)
    │   └── Embeds query → cosine distance in ChromaDB
    └── BM25 keyword search: _bm25_search(k=k*2)
        └── Tokenize query → BM25Okapi scoring on all chunks
    ↓
Reciprocal Rank Fusion (RRF)
    └── score(doc) = Σ 1 / (rank + 60) across both result lists
        (60 is the standard constant from the original RRF paper)
    ↓
Top-k fused chunks (default k=8)
    ↓
LangChain ChatPromptTemplate
    ├── System prompt (Product Engineer persona, faithfulness rules)
    ├── MessagesPlaceholder (conversation history as HumanMessage/AIMessage)
    ├── Context string (joined chunks with "---" separators)
    └── User question
    ↓
Groq LLM (llama-3.1-8b-instant, temperature=0)
    ↓
Response:
    ├── /api/query → full JSON with answer + sources
    └── /api/query/stream → SSE tokens yielded one by one
            data: {"sources": [...]}
            data: {"token": "Tiago"}
            data: {"token": " is"}
            ...
            data: [DONE]
```

---

## Key Technical Decisions

| Decision | The "Why" |
|---|---|
| **FastAPI over Flask/Django** | Async-first (needed for streaming SSE), automatic OpenAPI docs at `/docs`, Pydantic validation integrated |
| **Llama 3.1 8B via Groq** | Free tier available, fast inference (~100ms), sufficient quality for the task. Tried different models during development. |
| **Local embeddings (fastembed) over OpenAI embeddings** | Zero API cost, ~1ms latency vs ~200ms for remote APIs, works offline, small model (~80MB) |
| **ChromaDB over Pinecone/Weaviate** | Local persistence, no external service, simple Python API, free |
| **Hybrid search (semantic + BM25) instead of pure semantic** | Semantic search alone misses exact technical terms like "FastAPI" when embeddings don't capture them well. BM25 catches them. RRF combines the strengths without needing to tune a weight. |
| **Reciprocal Rank Fusion (RRF) over weighted sum** | Parameter-free (no weight tuning), robust across query types, standard in information retrieval literature |
| **Section-aware chunking over fixed-size chunking** | Naive 500-char splits break sentences and lose context. Detecting sections (via markdown headings or PDF font-size analysis) keeps coherent content together. |
| **Pre-build ingestion in Dockerfile** | t3.micro has only 1GB RAM — loading fastembed + ChromaDB + ingesting chunks at startup caused OOM crashes. Baking the vector store into the image solves this. |
| **Streaming SSE over WebSockets** | Simpler (one-way server → client), works through standard HTTP proxies, no connection upgrade, good browser support via Fetch API ReadableStream |
| **Vanilla HTML/JS over React** | Single file, no build step, loads instantly, zero dependencies for the chat UI. The backend does the heavy lifting. |
| **Nginx reverse proxy over direct FastAPI exposure** | SSL termination via Let's Encrypt, standard security posture, handles port 80 → 443 redirect |
| **temperature=0 on the LLM** | Deterministic responses — critical for RAGAS evaluation consistency and for recruiter-facing reliability |
| **Gemini as RAGAS evaluator (not Groq)** | Best practice: use a different, stronger model to judge than the one generating. Prevents self-evaluation bias. |

---

## Hybrid Search Implementation Details

### Semantic Search (ChromaDB)
- Query is embedded with `FastEmbeddings` wrapper
- Cosine similarity search via `vector_store.similarity_search(query, k=k*2)`
- Retrieves **2× the final k** to give RRF more candidates to fuse
- Optional `document_id` filter to scope to a single uploaded document

### BM25 Keyword Search
- Implemented via `rank_bm25`'s `BM25Okapi` class
- **Index is built once, lazily on first query**, cached in module globals (`_bm25_index`, `_bm25_corpus`)
- Tokenizer: `re.findall(r"\w+", text.lower())` — simple regex word splitting, case-insensitive
- Scores all chunks against the tokenized query, returns top-k

### Reciprocal Rank Fusion
```
for rank, doc in enumerate(semantic_results):
    rrf_scores[key] += 1.0 / (rank + 60)
for rank, doc in enumerate(bm25_results):
    rrf_scores[key] += 1.0 / (rank + 60)
```
- Each document's final score is the sum of `1 / (rank + 60)` across both result lists
- Constant **60** is standard from the original RRF paper (Cormack et al.)
- Documents appearing in both lists get boosted naturally
- No weight tuning needed — this is why RRF is preferred over weighted sum

### Deduplication
Documents are keyed by the first 100 characters of content. When the same chunk appears in both semantic and BM25 results, its scores are summed instead of counted twice.

---

## Section-Aware Chunking

### Markdown Ingestion
```python
def _extract_markdown_sections(text) -> list[tuple[str, str]]:
    # Split by ATX headings (# ## ###)
    # Returns list of (section_title, section_text)
```
- Reads markdown line by line
- Starts a new section whenever a line begins with `#`
- Each section's title is extracted (stripping `#` prefix)
- Section text includes the title as its first line

### PDF Ingestion (Font-Size Heading Detection)
For PDFs, uses **PyMuPDF (fitz)** to detect headings by font size rather than relying on structural metadata:

1. **First pass:** collect all text span font sizes across the entire document
2. **Compute median** font size of body text
3. **Threshold:** `heading_threshold = median_size * 1.15` (15% larger than median)
4. **Second pass:** flag any line where `max_span_size >= threshold` AND line length < 60 chars as a heading
5. Group subsequent text under the most recent heading

**Why this works:** Most PDFs don't have reliable structural metadata. Font-size analysis is a heuristic that handles diverse document styles without needing OCR or external tools. The 15% threshold catches bold section titles without false-positive-ing on emphasized body text.

### Chunking Strategy
```python
if len(section_text) <= chunk_size:  # 500 chars
    chunks.append(section_text)       # Keep whole
else:
    sub_chunks = splitter.split_text(section_text)
    for sub_chunk in sub_chunks:
        chunks.append(f"{section_title}\n{sub_chunk}")  # Prefix with section
```
- Small sections stay whole for maximum coherence
- Large sections are split with `RecursiveCharacterTextSplitter` (chunk_size=500, overlap=50)
- Each sub-chunk is prefixed with its section title so retrieval keeps the topical context

### Metadata Stored Per Chunk
- `document_id` (UUID) — which document this chunk came from
- `filename` — original filename
- `page` — page number (1 for Markdown, actual page for PDFs)
- `section` — the section title this chunk belongs to

---

## Streaming SSE Implementation

### Backend (`stream_query` in retrieval.py)
```python
async def stream_query(question, document_id, history) -> AsyncGenerator[str, None]:
    # 1. Retrieve chunks
    results = _hybrid_search(...)

    # 2. First yield: sources for attribution
    yield f"data: {json.dumps({'sources': sources})}\n\n"

    # 3. Stream tokens from LangChain chain
    async for chunk in chain.astream({...}):
        if chunk.content:
            yield f"data: {json.dumps({'token': chunk.content})}\n\n"

    # 4. Final done marker
    yield "data: [DONE]\n\n"
```

### Headers (`routes.py`)
```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no  # prevents Nginx from buffering
```
The `X-Accel-Buffering: no` header is critical — without it, Nginx would buffer the entire response before sending it, defeating the purpose of streaming.

### Frontend Consumption
Uses Fetch API's ReadableStream:
```javascript
const response = await fetch('/api/query/stream', { ... });
const reader = response.body.getReader();
// Read SSE chunks one by one, parse JSON, append tokens incrementally
```
Tokens are appended to a text buffer and re-rendered via `marked.parse()` on each token — creating the live markdown rendering effect as text streams in.

---

## API Endpoints

```
GET  /                        — Serves the chat UI
GET  /health                  — Health check: {"status":"ok"}
GET  /static/*                — Static files (OG image, etc.)

POST /api/upload              — Upload a PDF for ingestion
     Body: multipart/form-data with "file"
     Returns: {document_id, filename, chunks_count}

POST /api/query               — Non-streaming query
     Body: {question, document_id?, history}
     Returns: {answer, sources}

POST /api/query/stream        — Streaming query (SSE)
     Body: {question, document_id?, history}
     Returns: SSE stream of sources + tokens + [DONE]

GET  /api/documents           — List all ingested documents
     Returns: [{document_id, filename}, ...]
```

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | required | Your Groq API key (free at console.groq.com) |
| `LLM_MODEL` | `llama-3.1-8b-instant` | Groq model to use |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model |
| `CHROMA_PATH` | `./chroma_db` | ChromaDB persistence directory |
| `CHUNK_SIZE` | `500` | Max characters per chunk |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |
| `RETRIEVAL_K` | `8` | Number of chunks retrieved per query (after RRF) |
| `GOOGLE_API_KEY` | optional | For RAGAS evaluation only (Gemini as judge) |

---

## Production Deployment — AWS EC2

### Infrastructure
- **Instance:** AWS EC2 t3.micro (1GB RAM, 2 vCPUs, free tier eligible)
- **Region:** eu-central-1 (Frankfurt)
- **OS:** Amazon Linux 2023
- **Domain:** `chatbot.tifortunato.com` (subdomain of `tifortunato.com`, registered via Namecheap)
- **DNS:** Namecheap A record pointing to EC2 public IP
- **SSL:** Let's Encrypt via Certbot, auto-renewal via cron

### Deployment Stack
- **Docker** container managed with `--restart unless-stopped`
- **Nginx** reverse proxy on ports 80/443 → container on `127.0.0.1:8000`
- **HTTP → HTTPS redirect** enforced by Nginx config
- **Swap space** (1GB) added to handle Docker builds without OOM
- **Container binding:** `127.0.0.1:8000:8000` (localhost only) — Nginx is the only public-facing surface

### Nginx Configuration
```nginx
server {
    listen 80;
    server_name chatbot.tifortunato.com;
    # ... Certbot handles 443 block and HTTP → HTTPS redirect

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;            # Critical for SSE streaming
        proxy_cache off;
        chunked_transfer_encoding on;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
    }
}
```

### Deployment Flow
1. Push code to GitHub `main` branch
2. SSH into EC2
3. `cd ~/ai-career-assistant && git pull origin main`
4. `sudo docker build -t career-chatbot .` (pre-ingests knowledge bases)
5. `sudo docker stop chatbot && sudo docker rm chatbot`
6. `sudo docker run -d --name chatbot --restart unless-stopped --env-file .env -p 127.0.0.1:8000:8000 career-chatbot`
7. Container auto-restarts on failure

---

## Evaluation — RAGAS Pipeline

The project includes `eval_ragas.py` — an automated quality evaluation script that:
1. Queries the live chatbot with 10 test questions
2. Collects answers + retrieved contexts
3. Scores each against a ground-truth reference using **Gemini 2.5 Flash as the evaluator LLM**
4. Outputs per-question breakdown and overall averages
5. Saves results to `ragas_results.csv` for tracking improvements over time

### Metrics Evaluated
- **Faithfulness** — Are factual claims in the answer grounded in the retrieved context? (Detects hallucinations)
- **Answer Relevancy** — Does the answer actually address the question?
- **Context Precision** — Are the retrieved chunks relevant to the question?
- **Context Recall** — Were all the relevant chunks retrieved?

### Why Gemini as Judge Instead of Groq?
Best practice in LLM evaluation: **use a different (ideally stronger) model as the judge** than the one generating the answers. Using the same model introduces self-evaluation bias — the model tends to agree with its own outputs. Gemini 2.5 Flash is a separate, capable evaluator on a free tier.

---

## Performance Optimizations for t3.micro

The t3.micro's 1GB RAM is a real constraint. Several deliberate choices accommodate it:

1. **Pre-build ingestion** — vector store is built during `docker build`, not at runtime startup
2. **Local embeddings** — avoids latency and cost of remote embedding APIs
3. **Small embedding model** — `BAAI/bge-small-en-v1.5` is only ~80MB (vs 400MB+ for larger models)
4. **retrieval_k=8** — keeps context window small enough for fast Groq inference
5. **BM25 index is lazy** — built on first query, not at startup (saves RAM during cold start)
6. **Container binds to 127.0.0.1** — no extra memory for public network stack; Nginx handles external traffic
7. **Swap space (1GB)** — backstop for Docker builds that briefly exceed 1GB

---

## Known Limitations & Future Improvements

### Current Limitations
- **RAGAS scores bounded by Llama 3.1 8B** — Faithfulness around 0.5 is the ceiling for this model size on a knowledge-heavy task. A stronger model (GPT-4, Claude) would score significantly higher with the same retrieval.
- **No query expansion** — Tried LLM-based query expansion but it hurt precision more than it helped recall. Removed.
- **BM25 index rebuilt on restart** — Lazy initialization means the first query after container start is slower. Could be pre-built at startup if memory allowed.
- **No conversation history limit** — long conversations could exceed the LLM's context window. Need sliding window or summarization.
- **Thesis PDF (~3MB, 85 pages) excluded** — too large to ingest on t3.micro. Key content was extracted into `knowledge_base.md` as markdown summaries instead.

### Future Improvements
- **Cross-encoder reranking** — retrieve 20 chunks, rerank to top 8 with a small cross-encoder model (memory-permitting)
- **Conversation summarization** — summarize old turns instead of truncating
- **Upgrade to t3.small (2GB)** — would allow larger embedding models, more chunks, and cross-encoder reranking
- **Structured output** — use LangChain's structured output for responses with cited source IDs per claim
- **A/B testing infrastructure** — to measure the impact of prompt/retrieval changes on real users

---

## RAG Chatbot Q&A

**Q: What does the AI Career Assistant do?**
A: It's a RAG chatbot that acts as Tiago Fortunato's interactive professional profile. Recruiters ask natural-language questions about his experience, projects, and skills, and receive accurate, sourced answers in real time with streaming responses. Live at [chatbot.tifortunato.com](https://chatbot.tifortunato.com).

**Q: What is RAG and why use it for this?**
A: RAG (Retrieval-Augmented Generation) combines document retrieval with LLM generation. Instead of relying only on what the LLM was trained on, you retrieve relevant documents first and let the model ground its answers in them. This reduces hallucinations and lets the chatbot answer questions about content it was never trained on — like Tiago's specific projects and experience.

**Q: What's the retrieval architecture?**
A: Hybrid search combining semantic similarity (ChromaDB vector store) and keyword matching (BM25), fused using Reciprocal Rank Fusion. Semantic search captures meaning; BM25 catches exact technical terms the embedding might miss. RRF combines both without needing to tune a weight parameter.

**Q: Why hybrid search instead of pure semantic search?**
A: Pure semantic search alone misses exact technical terms like "FastAPI" or "ChromaDB" when the embedding model doesn't perfectly capture them. BM25 is a keyword-based algorithm that catches exact matches. Combining both via RRF gets the best of both worlds — meaning-based AND exact-keyword retrieval.

**Q: How does Reciprocal Rank Fusion work?**
A: RRF scores each document by `1 / (rank + 60)` across multiple result lists, then sums the scores. Documents appearing in multiple lists naturally get boosted. The constant 60 comes from the original RRF paper and doesn't need tuning. It's parameter-free, which is why it's preferred over weighted sum approaches.

**Q: How is the knowledge base chunked?**
A: Section-aware chunking. For Markdown files, it splits by ATX headings (# ## ###). For PDFs, it uses PyMuPDF to analyze font sizes — the median font size across all text spans is computed, and any line with font size 15% larger than median is flagged as a heading. Small sections stay whole (better context); large sections are split with RecursiveCharacterTextSplitter (chunk_size=500, overlap=50) and each sub-chunk is prefixed with its section title.

**Q: Why not use a larger chunk size?**
A: Tried chunk_size=800 but it actually hurt RAGAS scores during evaluation. With 500-char chunks + 50-char overlap + section title prefix, each chunk has enough context without diluting retrieval precision.

**Q: Why local embeddings instead of OpenAI?**
A: BAAI/bge-small-en-v1.5 runs locally via fastembed. It's a ~80MB model that produces 384-dimensional vectors with ~1ms latency per embedding. Compared to OpenAI's ada-002: zero API cost, much faster (no network round-trip), works offline, and sufficient quality for the 500-char chunks being embedded. The slight quality gap vs ada-002 is negligible for this size of knowledge base.

**Q: Why Groq specifically?**
A: Inference latency. Groq's LPU architecture gets Llama 3.1 8B responses back fast enough for streaming to feel instant. Free tier is generous (6000 tokens per minute). For a recruiter-facing chatbot, response speed matters — slow responses kill engagement.

**Q: How does streaming work?**
A: Server-Sent Events (SSE). The backend uses an async generator in FastAPI's StreamingResponse. It first yields the sources as JSON, then streams LLM tokens one at a time as they come back from `chain.astream()`, and finally yields a `[DONE]` marker. The frontend consumes this with Fetch API's ReadableStream and re-renders markdown incrementally as tokens arrive — creating a ChatGPT-like effect.

**Q: Why SSE instead of WebSockets?**
A: SSE is simpler (one-way server → client, no connection upgrade), works through standard HTTP proxies without configuration, has good native browser support, and doesn't need a separate WebSocket server. For a chat that only needs server-to-client streaming, WebSockets are overkill.

**Q: How is the Nginx proxy configured for streaming?**
A: The key setting is `proxy_buffering off`. By default, Nginx buffers responses, which would defeat SSE by collecting the entire stream before sending it. With `proxy_buffering off` and `X-Accel-Buffering: no` on the response headers, tokens are flushed through immediately.

**Q: Why pre-ingest the knowledge base at Docker build time?**
A: The t3.micro has only 1GB RAM. Loading fastembed (~80MB), ChromaDB, and ingesting ~100 chunks at startup all at once causes OOM crashes. By running the ingestion during `docker build` (where memory pressure is lower), the vector store is baked into the image. At runtime, the container only reads the pre-built ChromaDB — much less memory pressure.

**Q: How does conversation history work?**
A: Short queries (fewer than 5 words) get enriched with the last 2 conversation exchanges before being sent to retrieval. This resolves references like "tell me more about the first one" where the search query alone has no meaningful keywords. Longer, specific queries are used as-is to avoid diluting retrieval. History is also passed to the LLM via LangChain's MessagesPlaceholder so the model can reference prior turns.

**Q: How are responses kept faithful to the context?**
A: Three mechanisms:
1. System prompt rules — "every factual claim must be grounded in context, never invent facts/metrics/outcomes", plus explicit example of what NOT to do
2. Temperature=0 for deterministic output (no random creativity)
3. The prompt explicitly says "if you don't have the information, say so" instead of filling gaps

**Q: How do you evaluate the chatbot's quality?**
A: RAGAS (Retrieval-Augmented Generation Assessment). It's a Python framework that uses an LLM as a judge to score four metrics: Faithfulness (claims grounded in context?), Answer Relevancy (does it address the question?), Context Precision (are retrieved chunks relevant?), and Context Recall (were the right chunks retrieved?). The `eval_ragas.py` script queries the live chatbot with 10 test questions and gets scored by Gemini 2.5 Flash — not Groq, to avoid self-evaluation bias.

**Q: Why Gemini as the RAGAS evaluator instead of Groq?**
A: Best practice in LLM evaluation: the judge should be a different (ideally stronger) model than the one generating. Using the same model introduces self-evaluation bias. Gemini 2.5 Flash is a separate, capable evaluator with a generous free tier.

**Q: How is the chatbot deployed?**
A: AWS EC2 t3.micro (1GB RAM, Frankfurt region) running Docker. Nginx reverse proxy on 443 handles SSL (Let's Encrypt). Container binds to `127.0.0.1:8000` — Nginx is the only public surface. Custom domain `chatbot.tifortunato.com` via Namecheap DNS A record. Let's Encrypt auto-renewal via cron. `--restart unless-stopped` keeps the container alive through crashes.

**Q: Why AWS EC2 instead of a managed service like Render?**
A: Previously deployed on Render (free tier) but moved to EC2 for: (1) always-on (Render free tier spins down after inactivity), (2) full control over the infrastructure, (3) custom domain + HTTPS setup as a learning experience, (4) no cold-start delays. Render was easier but EC2 is the production setup.

**Q: What's the memory constraint on t3.micro?**
A: 1GB RAM is the main bottleneck. Had to optimize: pre-build ingestion instead of runtime, small embedding model, limited retrieval_k, 1GB swap space as backstop, container binds to localhost only. Adding more features (thesis PDF ingestion, larger embeddings, cross-encoder reranking) would require upgrading to t3.small.

**Q: What tests exist?**
A: 11 Pytest tests across `test_health.py` (3 tests), `test_query.py` (5 tests), and `test_upload.py` (3 tests). They cover the health endpoint, query endpoint with and without history, streaming endpoint, and PDF upload with validation. GitHub Actions CI runs them on every push.

**Q: What was the hardest part of building this?**
A: Fitting the RAG pipeline into 1GB RAM. Every attempt to make it "better" (larger embeddings, bigger chunks, more retrieved chunks, thesis PDF ingestion) hit OOM errors on the t3.micro. Had to learn when "enough" is actually enough. The final config (500-char chunks, small embeddings, k=8, pre-build ingestion) is the sweet spot between quality and what the hardware can actually run.

**Q: What would you do differently next time?**
A: (1) Start with a bigger instance for development and only optimize down at the end. (2) Skip query expansion — tried it, added latency without helping scores. (3) Write evaluation tests (RAGAS) from day one instead of as an afterthought. (4) Plan the knowledge base structure before writing it — section sizes and titles directly affect retrieval quality.

**Q: Is the chatbot using RAG for every query, or does it just answer from memory sometimes?**
A: Every query goes through retrieval. There's no short-circuit. Even "hello" triggers a search — the RAG pipeline retrieves the top-k chunks regardless, and the LLM uses them or ignores them based on relevance. This ensures consistency: every answer is grounded in the same pipeline, never in the LLM's training data alone.

**Q: How do URLs in responses work?**
A: The system prompt explicitly requires markdown link formatting: `[display text](https://full-url)`. The frontend uses marked.js with a custom renderer that adds `target="_blank" rel="noopener noreferrer"` to all links, so clicking a link opens in a new tab and preserves the chat history.
