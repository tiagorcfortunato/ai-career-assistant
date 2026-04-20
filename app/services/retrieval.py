"""
app/services/retrieval.py — RAG Query Pipeline (the "brain")

The public API is `query()` and `stream_query()`. Both delegate to a LangGraph
StateGraph defined in app/services/graph.py. Orchestration lives in the graph;
the logic of each step (hybrid search, query routing, context formatting,
follow-up generation, rate-limit fallback) still lives in this file as
module-level helpers so the graph's nodes stay thin.

Pipeline (implemented as graph edges in graph.py):

1. ENRICH: If the query is short (<5 words), prepend conversation history
   to resolve follow-up references like "tell me more about that"
2. ROUTE: Keyword-match the question to a specific project file when possible
3. RETRIEVE (Hybrid): Semantic (Chroma) + keyword (BM25), fused via RRF
4. FORMAT: Prefix chunks with [SOURCE: <project>] labels
5. GENERATE: Stream tokens from Groq (Llama 3.3 70B → 8B fallback on 429)
6. FOLLOW-UPS: Second LLM call (8B) to suggest 3 next questions
7. Short-circuit: if retrieval is empty, jump to a friendly "no results" answer

Key design decisions:
- Hybrid search combines semantic understanding with exact keyword matching
- RRF fusion doesn't need tuning — it's parameter-free and robust
- History enrichment only for short queries (prevents context pollution on specific questions)
- Simple single-pass retrieval (no query expansion) to minimize latency and noise
- System prompt allows rephrasing but anchors all factual claims to retrieved context
- Token streaming is driven by astream_events on the graph — no separate streaming path
"""

import json
import logging
import re
import time
from typing import AsyncGenerator

from groq import RateLimitError
from langchain_groq import ChatGroq
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from rank_bm25 import BM25Okapi

from app.config import settings
from app.models.schemas import ChatMessage, QueryResponse, Source
from app.services.embeddings import FastEmbeddings

logger = logging.getLogger(__name__)

# Fallback model to use if the primary model is rate-limited
FALLBACK_MODEL = "llama-3.1-8b-instant"


def _get_llm(model: str | None = None) -> ChatGroq:
    """Return a ChatGroq instance. If model is None, uses the configured model."""
    return ChatGroq(
        model=model or settings.llm_model,
        api_key=settings.groq_api_key,
        temperature=0,
    )


FOLLOWUP_PROMPT = """You just answered this question about Tiago Fortunato:

Question: {question}
Answer: {answer}

Generate exactly 3 short follow-up questions a recruiter might ask next, based on this answer.
Rules:
- Each question under 12 words
- They should dig deeper into interesting details from the answer
- Do NOT repeat the original question
- Output ONLY the 3 questions, one per line, no numbering, no bullets, no quotes
- No preamble or explanation
"""


def _generate_followups(question: str, answer: str) -> list[str]:
    """
    Use a small/fast LLM to generate 3 contextual follow-up questions.
    Uses the fallback (8b) model since this is a lightweight task.
    Returns empty list on any failure — follow-ups are nice-to-have.
    """
    try:
        llm = _get_llm(FALLBACK_MODEL)  # always use 8b for speed/cost
        prompt = ChatPromptTemplate.from_messages([
            ("human", FOLLOWUP_PROMPT),
        ])
        chain = prompt | llm
        result = chain.invoke({"question": question, "answer": answer[:1500]})
        lines = [line.strip().lstrip("-•*0123456789. ").rstrip("?") + "?"
                 for line in result.content.split("\n") if line.strip()]
        # Filter out any very short or very long lines
        lines = [l for l in lines if 5 < len(l) < 120]
        return lines[:3]
    except Exception as e:
        logger.warning("Follow-up generation failed: %s", str(e)[:300])
        return []


SYSTEM_PROMPT = """You are the Professional Talent Assistant for Tiago Fortunato, a Software Engineer specialized in AI and Backend based in Berlin. Your goal is to help recruiters, hiring managers, and technical interviewers understand Tiago's technical depth and professional journey.

Rules:
- You may rephrase, restructure, and improve the clarity of information from the context. Sound natural and professional, not robotic.
- However, every FACTUAL CLAIM must be grounded in the context. You may say things differently, but you must not invent facts, metrics, outcomes, or achievements that are not in the context. For example: if the context says "live in production but no meaningful user traction yet", do NOT say "strong user base" or "proven track record of scalability".
- If the context does not contain enough information to fully answer the question, clearly state what you know from the context and what you don't. NEVER fill gaps with assumptions or general knowledge. Saying "I don't have that specific information" is better than guessing.
- Do NOT add generic advice, industry best practices, or common knowledge that is not in the context. Every sentence in your response should be traceable to a specific part of the context.
- NEVER invent statistics, percentages, user numbers, revenue figures, case studies, or metrics that are not explicitly stated in the context. If the context says a product has no user traction yet, do NOT fabricate success metrics. Saying "the product is live but doesn't have meaningful user data yet" is correct and honest.
- ALWAYS respond in English by default. Only switch to another language if the user explicitly writes their question in that language (Portuguese, German, etc.).
- Each context chunk starts with a [SOURCE: PROJECT NAME] label telling you which project it belongs to. CRITICAL: when a question asks about a specific project (e.g., "Tell me about Odys"), ONLY use chunks whose source matches that project. NEVER attribute features or technical details from one project to another. For example, features of the RAG Career Chatbot must never be described as features of Odys or the Inspection API, and vice versa.
- If you genuinely don't have the information, say so briefly and pivot to a related strength Tiago does have. You may suggest follow-up questions, but ONLY ones that highlight Tiago's strengths.
- Emphasize the Inspection Management API and the RAG Chatbot as core technical proofs of his work.
- When mentioning URLs or GitHub links, ALWAYS format them as markdown links: [display text](https://full-url). Never write raw URLs as plain text.
- CRITICAL: NEVER invent URLs. Only use URLs that appear verbatim in the context. If the context doesn't have a URL for something, DO NOT make one up (no "example.com/...", no guessed paths, no placeholder URLs). Instead, omit the link entirely and describe the resource in words.
- When showing code examples, use ONLY the exact code snippets from the context. NEVER generate, complete, or modify code. If the context has a code snippet, quote it exactly. If not, describe the pattern in words and link to the GitHub file instead.
- Adapt your language to the audience: if the question seems non-technical, explain concepts simply. If technical, go deep.
- Use markdown formatting: bold for emphasis, bullet points for lists, code blocks for technical details. Keep responses well-structured and scannable.
- When discussing projects, highlight both the WHAT (features) and the WHY (design decisions and trade-offs).

Context:
{context}"""


# ─── BM25 index (built once, reused across queries) ─────────────────────────

_bm25_index: BM25Okapi | None = None
_bm25_corpus: list[dict] = []  # stores {"content": ..., "metadata": ...}


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer for BM25."""
    return re.findall(r"\w+", text.lower())


def _build_bm25_index():
    """Build BM25 index from all documents in ChromaDB. Called once on first query."""
    global _bm25_index, _bm25_corpus

    vector_store = _get_vector_store()
    collection = vector_store._collection
    all_docs = collection.get(include=["documents", "metadatas"])

    if not all_docs["documents"]:
        return

    _bm25_corpus = [
        {"content": doc, "metadata": meta}
        for doc, meta in zip(all_docs["documents"], all_docs["metadatas"])
    ]

    tokenized = [_tokenize(doc["content"]) for doc in _bm25_corpus]
    _bm25_index = BM25Okapi(tokenized)


def _bm25_search(query: str, k: int = 20) -> list[dict]:
    """Keyword search using BM25. Returns top-k results with scores."""
    global _bm25_index, _bm25_corpus

    if _bm25_index is None:
        _build_bm25_index()

    if _bm25_index is None:
        return []

    tokenized_query = _tokenize(query)
    scores = _bm25_index.get_scores(tokenized_query)

    scored_docs = [
        {**_bm25_corpus[i], "score": scores[i]}
        for i in range(len(scores))
    ]
    scored_docs.sort(key=lambda x: x["score"], reverse=True)
    return scored_docs[:k]


# ─── Hybrid search with Reciprocal Rank Fusion ──────────────────────────────

def _hybrid_search(
    query: str,
    document_id: str | None,
    k: int = 10,
    allowed_files: list[str] | None = None,
) -> list[dict]:
    """
    Combines semantic search (ChromaDB) and keyword search (BM25) using
    Reciprocal Rank Fusion (RRF). This captures both meaning-based and
    exact-keyword matches — e.g., "FastAPI" matches even if the embedding
    doesn't capture the exact term well.

    RRF formula: score = sum(1 / (rank + 60)) across all result lists.
    The constant 60 is standard (from the original RRF paper).

    If `allowed_files` is provided, results are filtered to only those files.
    """
    vector_store = _get_vector_store()

    # Build filter: either document_id, file filter, or both
    if document_id:
        search_filter = {"document_id": document_id}
    elif allowed_files:
        if len(allowed_files) == 1:
            search_filter = {"filename": allowed_files[0]}
        else:
            search_filter = {"filename": {"$in": allowed_files}}
    else:
        search_filter = None

    # 1. Semantic search — retrieve more than needed for fusion
    semantic_results = vector_store.similarity_search(
        query=query,
        k=k * 2,
        filter=search_filter,
    )

    # 2. BM25 keyword search
    bm25_results = _bm25_search(query, k=k * 2)
    if document_id:
        bm25_results = [
            r for r in bm25_results
            if r["metadata"].get("document_id") == document_id
        ]
    if allowed_files:
        bm25_results = [
            r for r in bm25_results
            if r["metadata"].get("filename") in allowed_files
        ]

    # 3. Reciprocal Rank Fusion
    rrf_scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}
    rrf_k = 60  # standard RRF constant

    # Score semantic results
    for rank, doc in enumerate(semantic_results):
        key = doc.page_content[:100]  # use content prefix as key
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (rank + rrf_k)
        doc_map[key] = {
            "content": doc.page_content,
            "metadata": doc.metadata,
        }

    # Score BM25 results
    for rank, doc in enumerate(bm25_results):
        key = doc["content"][:100]
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (rank + rrf_k)
        if key not in doc_map:
            doc_map[key] = {
                "content": doc["content"],
                "metadata": doc["metadata"],
            }

    # 4. Sort by fused score and return top-k. The fused score is attached to
    # each chunk so downstream nodes (evaluate_retrieval) can gauge confidence
    # without re-running the search. Range is bounded above by 2/rrf_k ≈ 0.033
    # when a doc tops both lists, so thresholds must live in that range.
    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return [{**doc_map[key], "score": score} for key, score in ranked[:k]]


# ─── Vector store ────────────────────────────────────────────────────────────

def _get_vector_store() -> Chroma:
    embeddings = FastEmbeddings(model_name=settings.embedding_model)
    return Chroma(
        persist_directory=settings.chroma_path,
        embedding_function=embeddings,
    )


# ─── Query routing ──────────────────────────────────────────────────────────

# Map project keywords to knowledge base filenames. Retrieval can be filtered
# to only return chunks from matching files when the query clearly targets one.
PROJECT_KEYWORDS = {
    "odys_knowledge.md": [
        "odys", "whatsapp", "drizzle", "supabase", "stripe", "pix",
        "evolution api", "scheduling saas", "booking", "brazilian",
        "pgbouncer",
    ],
    "inspection_api_knowledge.md": [
        "inspection", "road damage", "pothole", "yolo", "vision model",
        "alembic", "jwt auth", "fastapi auth", "damage classification",
        "groq vision", "inspection management", "override",
    ],
    "rag_chatbot_knowledge.md": [
        "rag chatbot", "career assistant", "hybrid search", "bm25",
        "reciprocal rank fusion", "rrf", "streaming sse", "section-aware chunking",
        "chromadb", "fastembed", "this chatbot", "career bot",
    ],
}


def _route_query(question: str) -> list[str] | None:
    """
    Simple keyword-based query routing. If the question clearly targets a
    specific project, return [filename] to filter retrieval. If it's general
    or ambiguous, return None (search everything).
    """
    lower = question.lower()
    matched_files = [
        filename
        for filename, keywords in PROJECT_KEYWORDS.items()
        if any(kw in lower for kw in keywords)
    ]
    # If exactly one project is matched, scope to it. Multiple matches = general.
    if len(matched_files) == 1:
        # Always include the general knowledge_base.md for context
        return [matched_files[0], "knowledge_base.md"]
    return None


def _format_context(results: list[dict]) -> str:
    """
    Format retrieved chunks with clear project labels so the LLM knows
    which project each chunk belongs to and doesn't mix up features.
    """
    file_to_project = {
        "knowledge_base.md": "GENERAL PROFILE",
        "odys_knowledge.md": "ODYS (SaaS product)",
        "rag_chatbot_knowledge.md": "RAG CAREER CHATBOT (this chatbot)",
        "inspection_api_knowledge.md": "INSPECTION MANAGEMENT API",
    }
    formatted = []
    for doc in results:
        filename = doc["metadata"].get("filename", "unknown")
        project = file_to_project.get(filename, filename)
        formatted.append(f"[SOURCE: {project}]\n{doc['content']}")
    return "\n\n---\n\n".join(formatted)


def _build_search_query(question: str, history: list[ChatMessage]) -> str:
    """
    If there's conversation history AND the query is short/ambiguous,
    enrich the search query with recent context. This helps resolve
    references like "tell me more about the first one".
    """
    if not history or len(question.split()) >= 5:
        return question
    last_exchange = history[-2:] if len(history) >= 2 else history
    context = " ".join(m.content for m in last_exchange)
    return f"{context} {question}"


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Detect rate limit errors even when wrapped by LangChain or ExceptionGroup."""
    # Direct check
    if isinstance(exc, RateLimitError):
        return True
    # ExceptionGroup (Python 3.11+) — recursively check sub-exceptions
    if hasattr(exc, "exceptions"):
        return any(_is_rate_limit_error(sub) for sub in exc.exceptions)
    # Check __cause__ and __context__ chain
    if exc.__cause__ is not None and _is_rate_limit_error(exc.__cause__):
        return True
    if exc.__context__ is not None and _is_rate_limit_error(exc.__context__):
        return True
    # Fall back to string matching on the full traceback
    import traceback
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    tb_lower = tb.lower()
    return "rate limit" in tb_lower or "429" in tb or "rate_limit_exceeded" in tb_lower


def _invoke_with_fallback(chain, params: dict, prompt):
    """Invoke the LLM chain with the primary model, fall back to 8b on rate limit."""
    try:
        return chain.invoke(params)
    except Exception as e:
        if _is_rate_limit_error(e):
            logger.warning("Primary model rate-limited, falling back to %s: %s", FALLBACK_MODEL, str(e)[:200])
            fallback_chain = prompt | _get_llm(FALLBACK_MODEL)
            return fallback_chain.invoke(params)
        raise


async def query(
    question: str, document_id: str | None, history: list[ChatMessage]
) -> QueryResponse:
    """
    Delegates to the LangGraph StateGraph. The graph runs:
        enrich_query → route_query → retrieve →
            format_context → generate_answer → generate_followups → END
        (or, on empty retrieval: retrieve → fallback_response → END)
    """
    from app.services.graph import graph

    start = time.time()

    initial_state = {
        "question": question,
        "document_id": document_id,
        "history": history or [],
    }

    final_state = await graph.ainvoke(initial_state)

    duration = time.time() - start
    logger.info(
        "Query completed in %.2fs | question=%r | chunks=%d | routed=%s | followups=%d",
        duration,
        question[:80],
        len(final_state.get("retrieved_chunks", [])),
        bool(final_state.get("target_files")),
        len(final_state.get("follow_ups", [])),
    )

    return QueryResponse(
        answer=final_state["answer"],
        sources=final_state.get("sources", []),
        follow_ups=final_state.get("follow_ups", []),
    )


async def stream_query(
    question: str, document_id: str | None, history: list[ChatMessage]
) -> AsyncGenerator[str, None]:
    """
    Streaming version of query() — drives the same graph via astream_events
    and re-emits the events we care about as SSE:

      - retrieve node completes with chunks       → {"sources": [...]}
      - chat model stream from generate_answer    → {"token": "..."}
      - fallback_response completes               → {"token": "<friendly msg>"}
      - graph completes                           → {"follow_ups": [...]}
      - always                                    → [DONE]
    """
    from app.services.graph import graph

    start = time.time()

    initial_state = {
        "question": question,
        "document_id": document_id,
        "history": history or [],
    }

    final_state: dict = {}
    chunks_count = 0
    routed = False

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            data = event.get("data", {}) or {}

            # Token stream — only from the generate_answer node, not follow-ups
            if kind == "on_chat_model_stream":
                metadata = event.get("metadata", {}) or {}
                if metadata.get("langgraph_node") == "generate_answer":
                    chunk = data.get("chunk")
                    content = getattr(chunk, "content", "") if chunk is not None else ""
                    if content:
                        yield f"data: {json.dumps({'token': content})}\n\n"
                continue

            # Node completion events
            if kind == "on_chain_end":
                output = data.get("output") or {}

                if name == "retrieve" and isinstance(output, dict):
                    retrieved = output.get("retrieved_chunks", []) or []
                    chunks_count = len(retrieved)
                    if retrieved:
                        sources_payload = [
                            {
                                "content": doc["content"][:200],
                                "section": doc["metadata"].get("section", ""),
                                "page": doc["metadata"].get("page", 0),
                                "filename": doc["metadata"].get("filename", ""),
                            }
                            for doc in retrieved
                        ]
                        yield f"data: {json.dumps({'sources': sources_payload})}\n\n"

                elif name == "route_query" and isinstance(output, dict):
                    routed = bool(output.get("target_files"))

                elif name == "fallback_response" and isinstance(output, dict):
                    fallback_answer = output.get("answer", "")
                    if fallback_answer:
                        yield f"data: {json.dumps({'token': fallback_answer})}\n\n"

                elif name == "LangGraph" and isinstance(output, dict):
                    final_state = output

    except Exception as e:
        logger.error("Stream query failed: %s", e)
        if _is_rate_limit_error(e):
            yield f"data: {json.dumps({'token': 'Both models are rate-limited. Please try again in a few minutes.'})}\n\n"
        else:
            yield f"data: {json.dumps({'token': f'Error: {str(e)[:200]}'})}\n\n"

    follow_ups = final_state.get("follow_ups", []) if isinstance(final_state, dict) else []
    if follow_ups:
        yield f"data: {json.dumps({'follow_ups': follow_ups})}\n\n"

    duration = time.time() - start
    logger.info(
        "Stream query completed in %.2fs | question=%r | chunks=%d | routed=%s",
        duration, question[:80], chunks_count, routed,
    )
    yield "data: [DONE]\n\n"
