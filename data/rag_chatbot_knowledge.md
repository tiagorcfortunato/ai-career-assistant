# AI Career Assistant — RAG Chatbot Technical Deep Dive

> Technical knowledge base for the RAG Career Chatbot, Tiago Fortunato's production-deployed AI application built as a Retrieval-Augmented Generation system. Live at [chatbot.tifortunato.com](https://chatbot.tifortunato.com). Repository: [github.com/tiagorcfortunato/ai-career-assistant](https://github.com/tiagorcfortunato/ai-career-assistant).

---

## How This Chatbot Was Built — The Story

This is the making-of story for the AI Career Assistant. When someone asks "walk me through how this was built" or "how did you make this chatbot", respond with this narrative in a conversational, first-person tone (as if Tiago is telling the story).

**The starting point.** It began as a generic RAG PDF chatbot — upload any PDF, ask questions about it. A standard "RAG 101" project. But Tiago realized he had a stronger use case: turn it into his own interactive career assistant. Recruiters could ask about his experience instead of reading a static CV.

**The pivot.** The first big change was the knowledge base. Instead of ingesting random PDFs, Tiago wrote structured markdown files documenting his projects, background, and technical decisions. He also rewrote the system prompt with a Professional Talent Assistant persona focused on recruiters.

**The first deploy (Render).** The chatbot went live on Render's free tier. Fast to set up, free, worked. But two problems: (1) Render spins down after 15 minutes of inactivity, meaning 50-second cold starts for the first visitor; (2) Tiago wanted to show AWS experience on his portfolio.

**The AWS migration.** Tiago moved the chatbot to AWS EC2 (t3.micro). This meant setting up Docker, Nginx reverse proxy, Let's Encrypt SSL, custom domain (chatbot.tifortunato.com via Namecheap DNS), and an Elastic IP so the address wouldn't change on restart. All manual — no managed service hiding the complexity. This was deliberate: the point was to learn production infrastructure, not just to deploy.

**The retrieval problem.** Early answers were hit-or-miss. When asked "what's your tech stack?", the chatbot sometimes missed relevant chunks. The fix was hybrid search — combining semantic search (ChromaDB embeddings) with keyword search (BM25), fused via Reciprocal Rank Fusion. Semantic search alone missed exact terms like "FastAPI"; BM25 alone missed synonyms. Together, they cover both.

**The cross-project confusion.** Once Tiago added separate knowledge base files for Odys, the Inspection API, and the RAG chatbot itself, a new problem emerged: the LLM would attribute Odys features to the RAG chatbot or vice versa because the retrieved chunks didn't tell it which project they belonged to. The fix was two-fold: (1) prefix each retrieved chunk with a `[SOURCE: PROJECT NAME]` label so the LLM sees explicit project boundaries; (2) add query routing — a keyword-based classifier that, when the question clearly targets one project, filters retrieval to only that project's chunks.

**The memory problem.** The t3.micro has only 1GB RAM. Every attempt to make the chatbot "better" (larger embeddings, more chunks, ingesting a 3MB thesis PDF) hit OOM errors during Docker build. The solution was a combination of: pre-ingesting the knowledge base at Docker build time (so runtime startup was cheap), adding 1GB of swap space, and mounting ChromaDB as a persistent volume so container restarts don't re-ingest.

**The model upgrade.** The chatbot started on Llama 3.1 8B — fast but a bit shallow. Tiago upgraded to Llama 3.3 70B (also free on Groq, just with tighter rate limits). Responses became noticeably richer. Then he added automatic model fallback: if the 70B hits its daily rate limit, the chatbot silently switches to 8B so users never see errors.

**The evaluation pipeline.** To measure improvements objectively, Tiago built a RAGAS evaluation script. It queries the live chatbot with 10 test questions and scores the answers using Google's Gemini as the judge — a different model than the chatbot uses, to avoid self-evaluation bias. The metrics are faithfulness, answer relevancy, context precision, and context recall. Running RAGAS after each change showed which changes actually helped and which were noise.

**The UX polish.** Small details that make a big difference: streaming responses via SSE so text appears word-by-word like ChatGPT; conversation persistence in localStorage so recruiters can close the tab and come back later; a curated set of entry questions on the welcome screen (broad, welcoming) that transition to LLM-generated contextual follow-ups after the first interaction; links open in a new tab; markdown rendering with project-specific formatting.

**The follow-up system.** After each answer, a separate Groq call uses the fast 8B model to generate 3 contextual follow-up questions based on what was just discussed. These replace the static suggestions with questions that actually make sense for where the conversation is. Generic questions get specific follow-ups.

**The lesson.** The hardest part wasn't any single feature — it was learning when to stop adding features. Every improvement cycle had diminishing returns, and the RAGAS scores plateaued around 0.52 because Llama 8B hits a ceiling. Tiago learned to ship what works rather than chase scores, and to measure before optimizing. Most of the time he "improved" things without measuring, some of those changes hurt the scores.

**The takeaway for a recruiter.** This project shows: end-to-end product thinking (not just training a model), infrastructure work (Docker, Nginx, SSL, DNS, AWS), retrieval engineering (hybrid search, query routing, chunking), production LLM orchestration (streaming, fallback, rate limits), systematic evaluation (RAGAS with a separate judge), and attention to UX (entry points, persistence, contextual follow-ups).

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
- **Groq API** with **Llama 3.3 70B Versatile** (primary LLM, temperature=0) and **Llama 3.1 8B Instant** (automatic rate-limit fallback, plus follow-up-question generation)
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

## Embedding Model — BAAI/bge-small-en-v1.5 via fastembed

The chatbot embeds text using **`BAAI/bge-small-en-v1.5`**, executed via the **`fastembed`** library (ONNX runtime), **not** sentence-transformers.

**Model properties:**
- 384-dimensional embeddings
- ~80 MB on disk
- State-of-the-art in the small-model tier per the MTEB benchmark
- Sufficient semantic expressiveness for 500-character chunks

**Why not `bge-large`?** Would score 2-3 MTEB points higher but costs ~1.3 GB RAM to load. On a t3.micro (1 GB total RAM), this is OOM. Realistic only after instance upgrade.

**Why fastembed over sentence-transformers?**
1. **No PyTorch dependency.** sentence-transformers pulls torch + CUDA libs totalling 1-2 GB. fastembed uses the ONNX runtime, ~80 MB install footprint.
2. **t3.micro-friendly.** ONNX runs on CPU with ~10-50 ms per embed latency. No GPU needed.
3. **Cold-start behavior.** ONNX loads in ~200 ms; PyTorch models take significantly longer.

**Integration.** `FastEmbeddings` in `app/services/embeddings.py` is a thin adapter that implements LangChain's `Embeddings` interface (`embed_documents`, `embed_query`). ChromaDB consumes it like any other LangChain-compatible embedder.

**Clarification on ChromaDB's role.** ChromaDB is the vector database — it stores the embeddings produced by BGE. ChromaDB itself does not compute embeddings. The two components are distinct: the embedding model is `BAAI/bge-small-en-v1.5` (via fastembed), and the vector store is ChromaDB.

---

## LLM / Sprachmodell — Llama 3.3 70B via Groq (with 8B fallback)

*Which LLM does the chatbot use? Welches Sprachmodell nutzt der Chatbot für die Antwortgenerierung?*

The RAG Career Chatbot uses **two Llama models via the Groq API** for answer generation — a layered setup where the larger model answers by default and a smaller one catches rate-limit recovery and best-effort follow-up generation. This is the **primary LLM stack** of the chatbot, distinct from the embedding model (`BAAI/bge-small-en-v1.5` via fastembed) which only produces vectors.

**Primary LLM — `llama-3.3-70b-versatile`.** All user-facing answer generation runs through this 70B model via `ChatGroq` with `temperature=0` (deterministic output). Configured through the `LLM_MODEL` environment variable. Answers are streamed token-by-token via `.astream()` from the `generate_answer_node` in the LangGraph pipeline.

**Fallback LLM — `llama-3.1-8b-instant`.** Hard-coded in `app/services/retrieval.py` as `FALLBACK_MODEL`. Activated inside `generate_answer_node` via a `try/except` on Groq rate-limit errors (HTTP 429). The fallback lives as error recovery inside the node, **not** as a pipeline branch. The same 8B model also runs the separate `_generate_followups()` call that produces three follow-up question suggestions after each answer — best-effort, fails silently if the model errors.

**Why two tiers?** Llama 3.3 70B produces noticeably richer answers but has tighter daily rate limits on Groq's free tier. The 8B model is always available but shallower. The layered setup means users never see a 429 error — the worst case is a shallower answer from the 8B fallback for the duration of the rate-limit window. The RAGAS evaluation was originally run on the earlier 8B-only configuration, where Faithfulness plateaued around 0.5 due to model-size ceiling; a fresh evaluation against the 3.3 70B primary is pending.

**Why Groq and not OpenAI / Anthropic?** Groq's custom LPU (Language Processing Unit) hardware runs Llama 3.3 70B at 500+ tokens per second — compared to GPT-4's ~50 tokens/sec. For a streaming chatbot, that's the difference between feeling instant and feeling laggy. Groq's free tier is generous enough for portfolio traffic; at paid volume, per-token pricing sits below GPT-4 levels.

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
RRF candidate pool (retrieval_k = 20)
    ↓
Cross-encoder rerank → top-5 best-first (rag_rerank_top_k = 5)
    (feature-flagged; when flag is off in prod, RRF top-5 passed through as-is)
    ↓
Confidence gate: max_rerank_score >= 0.3 → continue, else → fallback_response
    ↓
LangChain ChatPromptTemplate
    ├── System prompt (Product Engineer persona, faithfulness rules)
    ├── MessagesPlaceholder (conversation history as HumanMessage/AIMessage)
    ├── Context string (joined chunks with "---" separators)
    └── User question
    ↓
Groq LLM — primary: llama-3.3-70b-versatile, temperature=0
        fallback on 429: llama-3.1-8b-instant
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

## LangGraph Orchestration

The retrieval pipeline is orchestrated via a **LangGraph `StateGraph`** with a typed `GraphState` TypedDict. The migration from LCEL to LangGraph was driven by a concrete need: branching logic.

**Why LangGraph over LCEL.** The original implementation was a linear LCEL chain (`prompt | llm`). As soon as branching was needed — first for the empty-retrieval fallback, later for the confidence-gate fallback — LCEL would have turned into nested `Runnable.bind()` calls with lambda glue, an if-spaghetti flow that is hard to test and extend. LangGraph makes the pipeline first-class:

- **Nodes are typed async functions** — each testable in isolation
- **Edges are declarative** — conditional routing via named functions
- **State is a TypedDict** with `total=False` — each node writes only the fields it produces, the runtime merges partial updates
- **Streaming comes for free** — `astream_events(version="v2")` emits typed events per node transition; `on_chat_model_stream` events from the `generate_answer` node are forwarded as SSE tokens to the browser

**Node sequence (execution order on every query):**
1. `enrich_query_node` — prepends conversation history to short follow-up queries (<5 words + history exists)
2. `route_query_node` — keyword-based project scoping (e.g. "odys" → `odys_knowledge.md` + `knowledge_base.md`)
3. `retrieve_node` — hybrid search: Chroma semantic similarity (k*2) + BM25 keyword (k*2), fused via Reciprocal Rank Fusion, top-20 candidates
4. `rerank_node` — Jina cross-encoder scoring, cut to top-5 (feature-flagged, disabled in prod due to t3.micro RAM budget)
5. `evaluate_retrieval_node` — writes confidence verdict: `"high"` if `max_rerank_score >= 0.3`, else `"low"`
6. **Conditional edge:** `"low"` → `fallback_response_node` (deterministic message, no LLM call) | `"high"` → `format_context_node`
7. `format_context_node` — builds `[SOURCE: PROJECT NAME]` labels per chunk
8. `generate_answer_node` — streams Llama 3.3 70B via Groq, with rate-limit fallback to Llama 3.1 8B
9. `generate_followups_node` — 3 follow-up questions via the 8B model, best-effort (fails silently)

**State schema:**
```python
class GraphState(TypedDict, total=False):
    question: str
    history: list[ChatMessage]
    document_id: str | None
    search_query: str
    target_files: list[str] | None
    retrieved_chunks: list[dict]
    reranked_chunks: list[dict]
    max_rerank_score: float
    confidence: str
    confidence_reason: str
    context: str
    answer: str
    sources: list[Source]
    follow_ups: list[str]
```

**Key architectural property.** LangGraph's separation of state, nodes, and edges makes every node individually testable (see `tests/test_rerank.py`, `tests/test_evaluate_retrieval.py`) and lets the full pipeline be exercised via either `graph.ainvoke()` (full response) or `graph.astream_events()` (streaming) — one pipeline, two consumption modes, zero duplication.

---

## Cross-Encoder Reranker & Confidence Gate

After the Reciprocal Rank Fusion stage returns the top-20 candidates, an optional cross-encoder reranker produces the final relevance scores that drive the confidence gate.

**Model.** `jinaai/jina-reranker-v2-base-multilingual` — a ~350 MB ONNX model that runs each (query, chunk) pair jointly through the transformer and emits one logit per pair. Sigmoid-normalised into `[0, 1]` range. Multilingual was a deliberate choice: traffic patterns mix German ↔ English, and the English-only alternative `ms-marco-MiniLM-L-6-v2` scored on-topic German queries at only ~0.12 — a gate failure caused by model language, not content irrelevance.

**Pipeline position.** After `retrieve_node` (RRF top-20), before `evaluate_retrieval_node` (confidence gate). The reranker writes `reranked_chunks` (top-5 best-first) and `max_rerank_score`; the gate then classifies `"high"` (≥ 0.3) or `"low"` (< 0.3 or no chunks).

**Feature flag.** `rag_rerank_enabled` — code default `True` (so dev and CI exercise the full pipeline), production override `False` via env var. Reason: the Jina ONNX model adds ~350 MB to the RAM footprint; together with embedder + Chroma + Python runtime on a t3.micro (1 GB total RAM), the reranker pushes the stack past OOM. Re-enabling is a single env flip after upgrading to t3.small.

**With flag off (current prod state):** `rerank_node` slices the RRF top-5 through as-is, writes `max_rerank_score = 1.0`, and the confidence gate effectively reduces to an empty check. The off-topic gate is missing, but the tight system prompt ("NEVER fill gaps with assumptions") keeps the LLM from hallucinating on off-topic queries.

**Lesson learned — signal separation before threshold tuning.** The first version of the confidence gate used the RRF fused score as the relevance signal, since it was already computed. Smoke tests then showed that on-topic and off-topic queries both produced scores in the ~0.03–0.08 range, and the gate fired almost randomly. The reason: RRF measures **rank position**, not semantic relevance — even an off-topic query produces values near the ceiling because *something* has to be rank 1. Switching to a cross-encoder score — which jointly scores (query, chunk) pairs — produced a **14× score separation**:

| Query type | Example | Top rerank_score |
|---|---|---|
| On-topic | *"Welche Tech Skills hat Tiago?"* | **0.807** |
| Off-topic | *"Wie ist das Wetter heute in Tokio?"* | **0.056** |

The broader lesson: when you build a gate, verify the signal separates your two classes *before* tuning the threshold. If on-topic and off-topic land in the same range, no threshold will save you.

---

## Key Technical Decisions

| Decision | The "Why" |
|---|---|
| **FastAPI over Flask/Django** | Async-first (needed for streaming SSE), automatic OpenAPI docs at `/docs`, Pydantic validation integrated |
| **Llama 3.3 70B Versatile via Groq (primary) + Llama 3.1 8B Instant (fallback)** | Groq's LPU hardware runs Llama 3.3 70B at 500+ tokens/sec (vs GPT-4's ~50) — makes streaming feel instant. Automatic fallback to 8B on 429 rate-limit errors keeps the chat responsive under load. The 8B model also powers best-effort follow-up-question generation (fails silently if that call errors). |
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
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Primary Groq model. 8B fallback (`llama-3.1-8b-instant`) is hard-coded in `retrieval.py` for 429 recovery + follow-up generation. |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model |
| `CHROMA_PATH` | `./chroma_db` | ChromaDB persistence directory (container mounts host volume here) |
| `CHUNK_SIZE` | `500` | Max characters per chunk |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |
| `RETRIEVAL_K` | `20` | RRF candidate pool size (before reranker narrows to `RAG_RERANK_TOP_K`) |
| `RAG_RERANK_MODEL` | `jinaai/jina-reranker-v2-base-multilingual` | Cross-encoder checkpoint used when rerank is enabled |
| `RAG_RERANK_TOP_K` | `5` | Post-rerank cut — how many chunks reach the LLM |
| `RAG_RERANK_MIN_SCORE` | `0.3` | Sigmoid-normalised threshold for the confidence gate |
| `RAG_RERANK_ENABLED` | `true` (code) / `false` (prod) | Feature flag — off in prod on t3.micro due to 350 MB RAM footprint of the Jina ONNX model |
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
4. **retrieval_k=20 (RRF candidate pool) → top-5 after reranking** — keeps the final LLM context window small for fast Groq inference while still feeding the reranker a rich candidate set
5. **BM25 index is lazy** — built on first query, not at startup (saves RAM during cold start)
6. **Container binds to 127.0.0.1** — no extra memory for public network stack; Nginx handles external traffic
7. **Swap space (1GB)** — backstop for Docker builds that briefly exceed 1GB

---

## Known Limitations & Future Improvements

### Current Limitations
- **Historical RAGAS ceiling at Faithfulness ≈ 0.5** — measured while the chatbot was still running on Llama 3.1 8B (before the upgrade to the current Llama 3.3 70B primary). The 8B model size was the bottleneck on this knowledge-heavy task; a fresh RAGAS pass against the 70B primary is pending. A stronger judge (GPT-4, Claude) over the same retrieval would also raise the ceiling.
- **No query expansion** — Tried LLM-based query expansion but it hurt precision more than it helped recall. Removed.
- **BM25 index rebuilt on restart** — Lazy initialization means the first query after container start is slower. Could be pre-built at startup if memory allowed.
- **No conversation history limit** — long conversations could exceed the LLM's context window. Need sliding window or summarization.
- **Thesis PDF (~3MB, 85 pages) excluded** — too large to ingest on t3.micro. Key content was extracted into `knowledge_base.md` as markdown summaries instead.

### Future Improvements
- **Re-enable cross-encoder reranking in production** — the reranker is already implemented (`jinaai/jina-reranker-v2-base-multilingual`, see "Cross-Encoder Reranker & Confidence Gate" above) but is feature-flagged off on t3.micro due to its ~350 MB RAM footprint. Upgrading to t3.small and flipping `RAG_RERANK_ENABLED=true` re-activates it — no code change
- **Conversation summarization** — summarize old turns instead of truncating
- **Upgrade to t3.small (2GB)** — would re-enable the reranker and allow larger embedding models
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
A: Inference latency. Groq's LPU hardware runs Llama 3.3 70B at 500+ tokens/sec (vs GPT-4's ~50), fast enough for streaming to feel instant. Free tier is generous for portfolio traffic. Automatic fallback to Llama 3.1 8B on 429 errors keeps the chat responsive under rate-limit pressure. For a recruiter-facing chatbot, response speed matters — slow responses kill engagement.

**Q: How many chunks are retrieved per query? Wie viele Chunks werden retrievt?**
A: **20 candidates from RRF, then cut to 5 after the cross-encoder reranker.** Specifically: each of the two searches (semantic via ChromaDB, keyword via BM25) returns `k*2 = 40` raw candidates. Reciprocal Rank Fusion merges them into a ranked top-`retrieval_k = 20` candidate pool. The cross-encoder reranker (when `RAG_RERANK_ENABLED=true`) scores each (query, chunk) pair jointly and narrows to `rag_rerank_top_k = 5` chunks — that top-5 is what the LLM actually sees. When the reranker is off in production (current state on t3.micro), the first 5 of the RRF top-20 are passed through as-is.

**Q: Which LLM / language model does this chatbot use for answer generation?**
A: The **primary LLM is `llama-3.3-70b-versatile`** via Groq, with `temperature=0` for deterministic output. When Groq returns a 429 rate-limit error, the `generate_answer_node` automatically falls back to `llama-3.1-8b-instant`. The same 8B model also runs the separate follow-up-question generation call (best-effort, fails silently). The 70B handles all user-facing answers by default; the 8B is a safety net, not the primary. (Note: the chatbot was originally built on 8B-only; it was later upgraded to the 70B primary + 8B fallback layered setup.)

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
A: Fitting the RAG pipeline into 1GB RAM. Every attempt to make it "better" (larger embeddings, bigger chunks, more retrieved chunks, thesis PDF ingestion) hit OOM errors on the t3.micro. Had to learn when "enough" is actually enough. The final config (500-char chunks, small embeddings, RRF candidate pool of 20 cut to top-5 after rerank, pre-build ingestion) is the sweet spot between quality and what the hardware can actually run.

**Q: What would you do differently next time?**
A: (1) Start with a bigger instance for development and only optimize down at the end. (2) Skip query expansion — tried it, added latency without helping scores. (3) Write evaluation tests (RAGAS) from day one instead of as an afterthought. (4) Plan the knowledge base structure before writing it — section sizes and titles directly affect retrieval quality.

**Q: Is the chatbot using RAG for every query, or does it just answer from memory sometimes?**
A: Every query goes through retrieval. There's no short-circuit. Even "hello" triggers a search — the RAG pipeline retrieves the top-k chunks regardless, and the LLM uses them or ignores them based on relevance. This ensures consistency: every answer is grounded in the same pipeline, never in the LLM's training data alone.

**Q: How do URLs in responses work?**
A: The system prompt explicitly requires markdown link formatting: `[display text](https://full-url)`. The frontend uses marked.js with a custom renderer that adds `target="_blank" rel="noopener noreferrer"` to all links, so clicking a link opens in a new tab and preserves the chat history.
