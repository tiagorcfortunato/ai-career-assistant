# How I migrated my RAG chatbot from LangChain to LangGraph

A chronological, warts-and-all log of the migration. Written as I went, so the
order of discoveries and mistakes is preserved.

---

## Starting point

- **Project**: a career-assistant RAG chatbot, live on Render, backed by FastAPI,
  ChromaDB, BM25 + RRF hybrid search, and Groq (Llama 3.3 70B with an 8B
  fallback). The knowledge base is a handful of markdown files that get
  auto-ingested on startup.
- **Why migrate?** The query pipeline worked — but it was a flat sequence of
  function calls inside `retrieval.py`, stitched together with a single LCEL
  pipe: `prompt | llm`. The branching ("no results → bail early") lived in an
  `if`. The rate-limit fallback lived in a `try/except`. The follow-up
  generation happened after the main call. None of this was *bad*, but as soon
  as I'd want to add a reranker, a query rewriter, or a validator, the
  imperative style would have turned into a pasta bowl.
- **LangGraph gives me the graph as a first-class object**: nodes, edges,
  conditional edges, and a single typed state that flows through them. The
  pipeline becomes inspectable, testable per-node, and trivially extensible.

The goal of this migration is **strict behavioral equivalence** — same
retrieval, same LLM calls, same SSE stream shape, same follow-up generation.
Only the orchestration changes.

---

## Plan (pre-implementation)

### Files to create
1. `app/services/graph.py` — the new home for the pipeline. Contains:
   - A `GraphState` `TypedDict` with 9 fields.
   - 7 async node functions, each a thin wrapper around an existing helper in
     `retrieval.py`.
   - A conditional edge function that routes from `retrieve` to either
     `format_context` (if we got chunks) or `fallback_response` (if not).
   - A module-level compiled graph singleton.

### Files to modify
2. `app/services/retrieval.py` — keep **every helper** (`_hybrid_search`,
   `_build_search_query`, `_route_query`, `_format_context`,
   `_generate_followups`, `_is_rate_limit_error`, `_invoke_with_fallback`,
   `_get_llm`, all the BM25 stuff, `SYSTEM_PROMPT`, `FOLLOWUP_PROMPT`). Rewrite
   only `query()` and `stream_query()` to delegate to the compiled graph.
3. `app/api/routes.py` — one-line change: `await retrieval.query(...)` because
   `query()` becomes async.
4. `tests/conftest.py` — the `mock_query` fixture patches `retrieval.query`.
   Since the route now `await`s it, the mock needs to return an awaitable.
   Swap `return_value=` for `new=AsyncMock(return_value=...)`.
5. `requirements.txt` — add `langgraph`.

### Verification
- `pytest tests/` still green.
- The streaming SSE shape (`sources` event → token events → `follow_ups` event
  → `[DONE]`) is preserved.

---

## Key design decisions

Before writing any code, I pinned down the decisions I'd otherwise keep
re-litigating mid-implementation:

1. **All nodes are async.** LangGraph supports either, but mixing is painful.
   Async lets `query()` use `graph.ainvoke(...)` and `stream_query()` use
   `graph.astream_events(...)` with the *same* node code. No parallel sync/async
   paths.

2. **Token streaming via `astream_events(version="v2")`.** I don't want to
   hand-roll a streaming path that bypasses the graph. Instead, the
   `generate_answer` node calls `chain.astream()` internally. LangGraph's
   streaming machinery emits `on_chat_model_stream` events automatically, and
   `stream_query()` re-emits those as SSE `{"token": ...}` events. One pipeline,
   two consumption modes.

3. **Sources are built inside the `retrieve` node**, not later. The raw chunks
   are only needed to (a) build the `Source` list and (b) format the context.
   Doing the `Source` construction once in the retrieve node is simpler than
   carrying raw chunks through to a downstream "build sources" step.

4. **Rate-limit fallback stays inside `_invoke_with_fallback`.** I *could* have
   modelled "primary failed → fall back to 8B" as two nodes with a conditional
   edge. But it's a transient-error recovery pattern, not a logical branch in
   the pipeline. Keeping it in a helper keeps the graph's edges about
   *semantics*, not *error handling*.

5. **Conditional edge condition reads state directly.** `state["retrieved_chunks"]`
   being empty is the condition. No separate success flag.

6. **Graph compiled once at module import.** Same pattern as the existing
   lazily-built BM25 index — pay the cost once.

---

## Step 1 — Add the dependency

`requirements.txt`:

```diff
 # LangChain
 langchain==0.3.0
 langchain-groq==0.2.0
 langchain-chroma==0.1.4
 langchain-community==0.3.0
+langgraph==1.1.6
```

I initially penciled in `langgraph==0.2.60` (the last 0.x release that plays
with `langchain==0.3.0`). But my environment already had `langgraph==1.1.6`
installed, and the APIs I need — `StateGraph`, `START`, `END`,
`add_conditional_edges`, `astream_events(version="v2")` — are stable across
the 0.2 → 1.x jump. Pinning to what's actually resolved in the env keeps
reality and the lockfile aligned.

---

## Step 2 — Create `app/services/graph.py`

This is the heart of the migration. A new file with three sections:

### 2a. The state (`GraphState`)

```python
class GraphState(TypedDict, total=False):
    question: str
    history: list[ChatMessage]
    document_id: str | None
    search_query: str
    target_files: list[str] | None
    retrieved_chunks: list[dict]
    context: str
    answer: str
    sources: list[Source]
    follow_ups: list[str]
```

Two decisions here:

- **`total=False`**: nodes populate fields incrementally. `answer` doesn't
  exist until `generate_answer` runs. Marking the TypedDict non-total means
  you're not lying to the type checker about what's present at each stage.
- **`document_id` is in state**, not passed as an argument somewhere else.
  Everything the graph needs to do its job travels in the state bag. No hidden
  parameters.

### 2b. The nodes

Each of the 7 nodes is an `async def` that takes `GraphState` and returns a
**partial** update dict. LangGraph merges these into the running state. The
node bodies are deliberately thin — the actual logic stays in the helpers in
`retrieval.py`. For example:

```python
async def enrich_query_node(state: GraphState) -> dict[str, Any]:
    from app.services import retrieval  # lazy to avoid circular import
    search_query = retrieval._build_search_query(
        state["question"], state.get("history", [])
    )
    return {"search_query": search_query}
```

**Problem encountered — circular imports.** The graph imports from
`retrieval`, and `retrieval` imports the compiled graph. If both imports
happened at module top level, Python would blow up. Fix: import `retrieval`
*inside* each node function (lazy import). It's ugly but localised. Once the
migration is done I can flip it — move the helpers into a separate
`_helpers.py` module that neither file needs to top-level-import — but for
a strictly-equivalent migration, laziness is the smaller change.

**The interesting node — `generate_answer_node`:**

```python
async def _astream_collect(llm) -> str:
    chain = prompt | llm
    buf = ""
    async for chunk in chain.astream(params):
        if chunk.content:
            buf += chunk.content
    return buf
```

Why `astream` and not `ainvoke`? Because I want one code path for both the
non-streaming API (`/query`) and the streaming API (`/query/stream`). When the
node uses `chain.astream()`:

- **Inside `graph.ainvoke()`** — the node accumulates chunks into `buf` and
  returns the full answer. The caller never sees the streaming.
- **Inside `graph.astream_events()`** — every chunk fires an
  `on_chat_model_stream` event that the SSE endpoint captures and re-emits.
  Token streaming without ever writing a token-emission loop in the endpoint.

This is the quiet win of the migration. The old code had *two* LLM call
paths: `chain.invoke()` in `query()` and `chain.astream()` in `stream_query()`.
Now there's one.

**The rate-limit fallback** stays as a local `try/except`:

```python
try:
    answer = await _astream_collect(retrieval._get_llm())
except Exception as e:
    if retrieval._is_rate_limit_error(e):
        answer = await _astream_collect(
            retrieval._get_llm(retrieval.FALLBACK_MODEL)
        )
    else:
        raise
```

I considered modelling this as a separate "fallback" node with a conditional
edge from `generate_answer`. Decided against it: the fallback is *error
recovery*, not a *logical* branch in the pipeline. The graph's edges should
encode semantics — "did we retrieve anything?" is semantic, "did the upstream
LLM 429?" is transient and belongs in the call site.

### 2c. Conditional edge

```python
def _route_after_retrieve(state: GraphState) -> str:
    if state.get("retrieved_chunks"):
        return "format_context"
    return "fallback_response"
```

This is the one branch point in the whole graph. Reads state directly — no
separate "retrieval_succeeded" flag.

### 2d. Graph assembly

```python
builder.add_conditional_edges(
    "retrieve",
    _route_after_retrieve,
    {
        "format_context": "format_context",
        "fallback_response": "fallback_response",
    },
)
```

The explicit mapping (third argument) looks redundant, but LangGraph 1.x
requires it: the function returns a string, and the dict tells the graph
which *node* that string maps to. This gives you the flexibility to return
"yes"/"no" from the condition function while the graph still knows to jump
to `"format_context"`/`"fallback_response"`.

`graph = build_graph()` runs at module import — compiled once per process.

### Conceptual explanation of each node

| Node | Responsibility | Writes |
|---|---|---|
| `enrich_query` | If the question is short (<5 words) and there's history, prepend the last two messages so retrieval has something to match against. | `search_query` |
| `route_query` | Keyword-match the question against project names. If exactly one project matches, scope retrieval to `[<that_project>.md, knowledge_base.md]`. | `target_files` |
| `retrieve` | Hybrid search. Semantic (Chroma) + keyword (BM25) merged via Reciprocal Rank Fusion. Also materialises the `Source` citation list. | `retrieved_chunks`, `sources` |
| `format_context` | Turn chunks into a prompt-ready string with `[SOURCE: ...]` labels so the LLM can tell projects apart. | `context` |
| `generate_answer` | System prompt + history + retrieved context → Llama 3.3 70B. Fallback to 8B on rate limit. | `answer` |
| `generate_followups` | A second, cheap LLM call (8B) that generates three follow-up questions based on the answer. Best-effort. | `follow_ups` |
| `fallback_response` | Short-circuit branch when retrieval came back empty. Returns a friendly "try asking about X" message. No LLM call. | `answer`, `sources`, `follow_ups` |

---

## Step 3 — Refactor `retrieval.py`

Two things changed in this file; everything else stayed put.

### 3a. `query()` became async and delegates to the graph

Before (~75 lines of orchestration):

```python
def query(question, document_id, history) -> QueryResponse:
    search_query = _build_search_query(question, history)
    allowed_files = _route_query(question)
    results = _hybrid_search(search_query, document_id, k=..., allowed_files=...)
    if not results:
        return QueryResponse(answer="I couldn't find...", sources=[])
    context = _format_context(results)
    prompt = ChatPromptTemplate.from_messages([...])
    chain = prompt | _get_llm()
    lc_history = [...]
    response = _invoke_with_fallback(chain, {...}, prompt)
    sources = [Source(...) for doc in results]
    follow_ups = _generate_followups(question, response.content)
    return QueryResponse(answer=response.content, sources=sources, follow_ups=follow_ups)
```

After (~20 lines, mostly logging):

```python
async def query(question, document_id, history) -> QueryResponse:
    from app.services.graph import graph

    initial_state = {
        "question": question,
        "document_id": document_id,
        "history": history or [],
    }
    final_state = await graph.ainvoke(initial_state)

    return QueryResponse(
        answer=final_state["answer"],
        sources=final_state.get("sources", []),
        follow_ups=final_state.get("follow_ups", []),
    )
```

The orchestration moved into the graph. The function is now an adapter between
the HTTP layer's arguments and the graph's state.

### 3b. `stream_query()` drives `astream_events`

This is the less obvious rewrite. The goal: preserve the existing SSE shape
byte-for-byte so the frontend doesn't need changes.

Mapping from old events to new event sources:

| Old code emitted… | New code emits it when… |
|---|---|
| `{"sources": [...]}` right after retrieval | `on_chain_end` with `name == "retrieve"` |
| `{"token": "..."}` per LLM chunk | `on_chat_model_stream` with `metadata.langgraph_node == "generate_answer"` |
| `{"token": "I could not find..."}` on empty | `on_chain_end` with `name == "fallback_response"` |
| `{"follow_ups": [...]}` at end | from final state accumulated on `on_chain_end` with `name == "LangGraph"` |
| `[DONE]` | always, in the `finally` portion |

**Problem encountered — cross-contamination from follow-ups.** The
`generate_followups_node` also triggers an LLM call. Without a filter, its
tokens would leak into the SSE stream and the user would see the follow-up
questions being dictated back to them. Fortunately, `_generate_followups`
uses `chain.invoke` (sync, no streaming), so no `on_chat_model_stream` events
fire. But I added the `metadata.langgraph_node == "generate_answer"` guard
anyway — defensive against a future change where someone swaps `invoke` for
`astream` in follow-ups.

**Problem encountered — which event carries the final state?** LangGraph
1.x emits `on_chain_end` for every node *and* for the root graph itself. The
root graph's `name` is `"LangGraph"`, and its `data.output` is the full final
state. I latch onto that to extract `follow_ups` at the end, rather than
tracking them via their own `on_chain_end` event (which would also work but
is one more branch in the stream handler).

### 3c. Import cleanup

Dropped `MessagesPlaceholder`, `HumanMessage`, `AIMessage` from
`retrieval.py` — they moved to `graph.py`. Also swapped the `ChatPromptTemplate`
import path from `langchain.prompts` to `langchain_core.prompts` (same class,
direct path; see the "problems" section below).

Kept every helper untouched: `_hybrid_search`, `_build_search_query`,
`_route_query`, `_format_context`, `_generate_followups`, `_is_rate_limit_error`,
`_invoke_with_fallback`, `_get_llm`, `_get_vector_store`, all the BM25 plumbing,
and both prompts. The migration's scope is *orchestration only*.

---

## Step 4 — Update `routes.py`

One line. `query()` is now async:

```diff
-        return retrieval.query(
+        return await retrieval.query(
             question=request.question,
             document_id=request.document_id,
             history=request.history,
         )
```

`stream_query()` was already consumed by `StreamingResponse` as an async
generator, so its call site didn't change.

---

## Step 5 — Update `tests/conftest.py`

The `mock_query` fixture patches `retrieval.query`. Since the route now
`await`s it, the mock must be awaitable:

```diff
-from unittest.mock import patch
+from unittest.mock import patch, AsyncMock
 ...
-    with patch("app.api.routes.retrieval.query", return_value=mock_response):
+    with patch(
+        "app.api.routes.retrieval.query",
+        new=AsyncMock(return_value=mock_response),
+    ):
```

The test files themselves didn't need to change — they hit the HTTP layer via
`TestClient` and never touch the async boundary directly. Clean.

---

## Problems encountered

### 1. Circular import between `retrieval.py` and `graph.py`

`graph.py` needs the helpers from `retrieval.py` (to wrap them in nodes), and
`retrieval.py`'s new `query()`/`stream_query()` need the compiled `graph` from
`graph.py`. If both imports happen at module top level, Python explodes.

**Fix**: lazy imports inside each node and inside `query`/`stream_query`:

```python
async def enrich_query_node(state: GraphState) -> dict[str, Any]:
    from app.services import retrieval  # lazy
    ...
```

It's the only ugly thing in the diff. The principled fix is to move the helpers
to a third module that neither file top-level-imports, but that's a separate
refactor — and this migration's goal is "change orchestration, touch nothing
else."

### 2. Pre-existing `.env` validation error

Running `pytest` gave:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
google_api_key
  Extra inputs are not permitted
```

The user's `.env` has a `GOOGLE_API_KEY` that the `Settings` class doesn't
declare. I confirmed this error reproduces on `main` before any of my changes
(`git stash` → `pytest` → same error). Out of scope for the migration. For
the verification run I temporarily renamed `.env` → `.env.bak`, ran pytest
with `GROQ_API_KEY=test-key` in the shell env, then restored `.env`. No code
change.

### 3. Pre-existing langchain version drift

After the `.env` workaround:

```
ImportError: cannot import name 'PipelinePromptTemplate' from 'langchain_core.prompts'
```

The installed `langchain==0.3.0` re-exports `PipelinePromptTemplate` from
`langchain_core.prompts`, but the installed `langchain_core` has moved on and
no longer provides that symbol. My `retrieval.py` imported
`ChatPromptTemplate` from `langchain.prompts`, which hits the broken
re-export chain on import.

**Fix**: switch the two affected imports (in `retrieval.py` and `graph.py`)
from `langchain.prompts` → `langchain_core.prompts`. Same class, direct
path, avoids the dead re-export. One-line change per file, and arguably
better style — `langchain_core` is the canonical home.

---

## Step 6 — Run tests

```
tests/test_health.py::test_health PASSED
tests/test_health.py::test_docs_available PASSED
tests/test_health.py::test_index_serves_html PASSED
tests/test_query.py::test_query_success PASSED
tests/test_query.py::test_query_with_history PASSED
tests/test_query.py::test_query_all_documents PASSED
tests/test_query.py::test_query_empty_question PASSED
tests/test_query.py::test_query_missing_question PASSED
tests/test_upload.py::test_upload_pdf_success PASSED
tests/test_upload.py::test_upload_non_pdf_rejected PASSED
tests/test_upload.py::test_upload_missing_file PASSED

====================== 11 passed, 600 warnings in 22.59s =======================
```

All green. The warnings are chromadb/pydantic deprecation noise unrelated
to the migration.

---

## Summary of what changed

| File | Status | What |
|---|---|---|
| `app/services/graph.py` | **new** (253 lines) | `GraphState` TypedDict, 7 async node functions, 1 conditional edge, compiled graph singleton. |
| `app/services/retrieval.py` | modified | `query()` and `stream_query()` rewritten to delegate to the graph. All helpers untouched. Import of `ChatPromptTemplate` moved to `langchain_core.prompts`. Dropped unused `MessagesPlaceholder`/`HumanMessage`/`AIMessage` imports. Module docstring updated. |
| `app/api/routes.py` | modified | `await retrieval.query(...)` (query is now async). |
| `tests/conftest.py` | modified | `mock_query` uses `AsyncMock` so the awaited route call gets back a real `QueryResponse`. |
| `requirements.txt` | modified | `+langgraph==1.1.6`. |
| `MIGRATION_LOG.md` | new | this file. |

Behavioural diff: none (or: none intended). Same retrieval, same LLM,
same streaming shape, same follow-ups, same rate-limit fallback, same
"no results" message.

What we got in return: a graph you can point at. If tomorrow I want to add a
reranker, it's one new node and two edge reassignments. If I want to branch
based on confidence score, it's a new conditional edge. The orchestration is
now *data*, not spaghetti.

---

## Addendum (2026-04-19): low-confidence fallback edge

The first post-migration payoff — and exactly the kind of change that motivated
moving to LangGraph in the first place. Production symptom: when retrieval
returned weak or off-topic chunks, the LLM would sometimes confidently paper
over the gap with a plausible-sounding answer. We had a fallback for the
*empty* retrieval case but nothing for the *weak* case.

### Shape of the change

A new node, `evaluate_retrieval`, sits between `retrieve` and `format_context`
and classifies the retrieval result as `"high"` or `"low"` confidence. The edge
that used to fork on `len(chunks) == 0` now forks on `confidence == "low"`,
which subsumes the old check and adds two more conditions.

    retrieve → evaluate_retrieval → {format_context | fallback_response}

The classifier is a pure function (`_evaluate_confidence`) so the tests don't
need to spin up the graph:

    low if:
      len(chunks) == 0                                   # old check
      or max(scores) < THRESHOLD_HI                      # weak top chunk
      or (len(chunks) < MIN_CHUNKS and max(scores) < THRESHOLD_MID)  # thin + mediocre

### Surfacing scores

`_hybrid_search` used to discard the fused RRF score after sorting — the tuple
was unpacked as `for key, _ in ranked[:k]`. I attached the score back onto
each returned chunk (`{**doc_map[key], "score": score}`) so the evaluate node
can read it without re-running any search. The downstream nodes ignore the
extra field and nothing else had to change.

### Thresholds are env-configurable

`RAG_THRESHOLD_HI`, `RAG_THRESHOLD_MID`, `RAG_MIN_CHUNKS` all live in `Settings`
with defaults 0.3 / 0.5 / 2. Those are the nominal values from the design
brief, written as if scores were in a [0, 1] similarity range. **The actual
RRF fused score is much smaller** — with two result lists at `rrf_k=60`, the
theoretical maximum is `2/60 ≈ 0.033`. So with the defaults as-written, every
query classifies as low-confidence and hits the fallback. Noted this in
`.env.example` with a suggested tuning (HI≈0.02, MID≈0.015) but left the
defaults matching the brief so tuning is an explicit, observable decision
rather than something I silently chose.

The `evaluate_retrieval_node` logs `confidence=... | reason=... | question=...`
on every invocation, which gives us the data to tune from after a day of
traffic — and also the foundation for a "low-confidence rate" metric in
whatever eval pipeline comes next.

### Why the node is thin

The node is two lines of logic around a pure function. I did that deliberately:
the graph node is the I/O wrapper (reads state, writes state, logs), the pure
function is the testable decision. Same separation as the retrieval helpers
vs. the retrieve node — orchestration here, logic there.

### Tests

`tests/test_evaluate_retrieval.py` hits every branch of the classifier without
touching ChromaDB, Groq, or the graph: empty, weak-top, few-and-mediocre,
happy path, single-strong-chunk, and a missing-score edge case. The existing
13 tests still pass; the total is now 20.

---

## Addendum (2026-04-20): RRF scores were the wrong gate — swapped in a cross-encoder reranker

Yesterday's low-confidence gate (`evaluate_retrieval` thresholding the max RRF
score) shipped with defaults copied from a design brief that assumed
similarity-style scores in `[0, 1]`. Two smoke tests revealed the real
problem, and it wasn't threshold tuning.

### What the smoke tests showed

With defaults pulled down to the observed RRF range (HI=0.02):

    Query                                        max RRF score    gate
    ─────────────────────────────────────────────────────────────────
    "Welche Tech Skills hat Tiago?"  (on-topic)   0.083           high
    "Wie ist das Wetter heute in Tokio?"  (off)   0.054           high

**Both queries looked equally confident to the gate.** Test 2 produced a
sensible answer only because the LLM's grounding prompt refused to
hallucinate — the gate never fired.

### Why RRF can't be the gate

RRF (`1/(rank + 60)`) is a *fusion* score. It encodes rank position across
two ranker outputs (semantic + BM25). The theoretical ceiling is ~0.033 when
a chunk tops both lists. That ceiling is reached by *whatever* chunk happens
to rank first — including the least-bad chunk for an off-topic query. RRF
was never trying to measure relevance; it's trying to combine rankings.
Using it as a relevance gate was my mistake.

### The fix: cross-encoder reranker

A cross-encoder scores `(query, chunk)` pairs *jointly* — same model sees
both strings, attends across them, outputs one logit per pair. That logit,
squashed through a sigmoid, is a real relevance signal bounded in `[0, 1]`.

New shape:

    retrieve → rerank → evaluate_retrieval → {format_context | fallback_response}

- `retrieve` widens the RRF candidate pool to 20 (was 10). Wider pool =
  better rerank quality; the cross-encoder will narrow back down.
- `rerank` calls `fastembed.rerank.cross_encoder.TextCrossEncoder`, applies
  sigmoid, sorts descending, keeps top-5 for the LLM. Attaches
  `rerank_score` to each chunk and writes `max_rerank_score` into state.
- `evaluate_retrieval` now gates on `max_rerank_score < RAG_RERANK_MIN_SCORE`
  (default 0.3) instead of the RRF fused score. RRF scores stay on chunks
  for debugging — they just don't gate anything.

### Why not cosine distance (the "shortcut")

Cosine distance between query and chunk embeddings is a *bi-encoder* signal
— each string is embedded independently, no cross-attention. Cheap, but
drops the interaction that makes a reranker a reranker. Production RAG has
largely moved to cross-encoder rerankers (Cohere Rerank, Jina reranker, BGE
reranker) for exactly this reason. Using cosine would've been fixing the
symptom (threshold semantics) while ignoring the diagnosis (we need an
actual relevance signal).

### Model choice: multilingual, not MS MARCO MiniLM

The brief asked for `Xenova/ms-marco-MiniLM-L-6-v2` — small, fast, ONNX. I
implemented against it first, then ran the smoke tests. The on-topic German
query scored sigmoid 0.12 — clean below the 0.3 default gate. MS MARCO is
English-only, and this chatbot's traffic is German ⟷ English. Rather than
paper over it by dropping the threshold, I switched the default to
`jinaai/jina-reranker-v2-base-multilingual`: same fastembed/ONNX pipeline,
no PyTorch dependency, just a multilingual checkpoint. Scores became:

    Query                                        max rerank    gate
    ─────────────────────────────────────────────────────────────────
    "Welche Tech Skills hat Tiago?"  (on-topic)   0.807         high
    "Wie ist das Wetter heute in Tokio?"  (off)   0.056         low

Now the gate actually separates the signal from the noise. The MS MARCO
model is still available — just set `RAG_RERANK_MODEL` in `.env` if your
corpus is English-only and you want a smaller model.

### Ops notes

- `fastembed 0.3.1 → 0.8.0`. `TextCrossEncoder` landed somewhere between
  those; `fastembed.rerank.cross_encoder` exists in 0.8. Still ONNX,
  still single-file install, no PyTorch/CUDA.
- `retrieval_k` default bumped `10 → 20`. The cross-encoder is cheap
  enough (~50-200ms for 20 pairs) that feeding it a wider candidate
  pool is essentially free and materially improves rerank quality.
- Sources (the UI citations) now materialise in the `rerank` node rather
  than `retrieve`. The SSE `sources` event fires after rerank, not
  after retrieve. That means the citations the UI shows match the chunks
  the LLM actually reasoned over — which is what "citation" implies.

### Lesson worth keeping

When you introduce a gate, verify the signal separates the classes before
you tune the threshold. Threshold tuning against a non-separating signal
just moves the failure mode around.

---

## What I'd do next (not part of this migration)

- Move `_hybrid_search`, `_route_query`, etc. into `app/services/_helpers.py`
  and kill the lazy imports.
- Add a reranker node between `retrieve` and `format_context`.
- Add a query-rewrite node that runs *before* `enrich_query`, using the LLM
  to reformulate ambiguous questions. That's exactly the kind of addition
  that would've been a mess in the old imperative code and is a single-node
  insert in the graph.
- Checkpoint the state to a sqlite backend via `langgraph.checkpoint.sqlite`
  so conversations become resumable.
- Fix the `.env`/`GOOGLE_API_KEY` drift and pin `langchain-core` so the
  environment stops being a trip hazard.
