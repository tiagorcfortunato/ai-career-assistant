"""
app/services/graph.py — LangGraph StateGraph for the RAG query pipeline

What used to be an imperative sequence inside retrieval.py is now a graph. The
work done in each step is unchanged — the node functions here just wrap the
existing helpers (_hybrid_search, _route_query, etc.) from retrieval.py.

Pipeline shape:

    START
      ↓
    enrich_query        ── rewrites short follow-up queries with history context
      ↓
    route_query         ── keyword-scopes retrieval to specific project files
      ↓
    retrieve            ── hybrid (semantic + BM25 + RRF) search
      ↓
    evaluate_retrieval  ── flags weak / empty / too-few chunks as "low confidence"
      ↓
    ┌─── confidence == "low"? ───┐
    │                            │
    ↓ no                         ↓ yes
    format_context               fallback_response
      ↓                            ↓
    generate_answer               END
      ↓
    generate_followups
      ↓
    END

Why a graph and not the old pipe (`prompt | llm`):
- Branching ("no results" short-circuit) is an edge, not an `if`.
- Each node has a single responsibility and can be tested in isolation.
- Token streaming comes for free via astream_events — the generate_answer node
  calls chain.astream(), and LangGraph emits on_chat_model_stream events that
  the SSE endpoint re-emits to the client.

Nodes are async so the same graph drives both the full-response API
(graph.ainvoke) and the streaming API (graph.astream_events).
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from app.config import settings
from app.models.schemas import ChatMessage, Source

logger = logging.getLogger(__name__)


class GraphState(TypedDict, total=False):
    """
    State flowing through the graph. Every node receives the full state and
    returns a partial update (dict of fields it wants to change).

    `total=False` because nodes populate fields incrementally — `answer` only
    exists after generate_answer runs, `follow_ups` only after
    generate_followups, etc.
    """
    question: str
    history: list[ChatMessage]
    document_id: str | None
    search_query: str
    target_files: list[str] | None
    retrieved_chunks: list[dict]
    confidence: str              # "high" | "low" — set by evaluate_retrieval_node
    confidence_reason: str       # human-readable reason, for logs + debugging
    context: str
    answer: str
    sources: list[Source]
    follow_ups: list[str]


# ─── Node functions ────────────────────────────────────────────────────────
#
# Each node is a thin wrapper around an existing helper in retrieval.py. The
# wrapping cost is deliberate: the graph is about *orchestration*, the helpers
# are about *logic*. Keeping them separate means this file reads as a pipeline
# and retrieval.py reads as a library.

async def enrich_query_node(state: GraphState) -> dict[str, Any]:
    """Prepend recent history to short queries so follow-ups like "tell me more
    about that" have enough context to retrieve against."""
    from app.services import retrieval  # lazy to avoid circular import

    search_query = retrieval._build_search_query(
        state["question"], state.get("history", [])
    )
    return {"search_query": search_query}


async def route_query_node(state: GraphState) -> dict[str, Any]:
    """Keyword-match the question against project names. If exactly one project
    matches, scope retrieval to that project's knowledge file (+ the general
    profile). Otherwise return None = search everything."""
    from app.services import retrieval

    target_files = retrieval._route_query(state["question"])
    if target_files:
        logger.info("Query routed to files: %s", target_files)
    return {"target_files": target_files}


async def retrieve_node(state: GraphState) -> dict[str, Any]:
    """Hybrid search: semantic (Chroma) + keyword (BM25), fused with RRF.
    Also builds the Source list here — the raw chunks are the authoritative
    source of both the LLM context *and* the citations, so we materialise both
    in the same node."""
    from app.services import retrieval

    chunks = retrieval._hybrid_search(
        query=state["search_query"],
        document_id=state.get("document_id"),
        k=settings.retrieval_k,
        allowed_files=state.get("target_files"),
    )

    sources = [
        Source(
            content=doc["content"][:200],
            page=doc["metadata"].get("page", 0),
            section=doc["metadata"].get("section", ""),
            document_id=doc["metadata"].get("document_id", ""),
        )
        for doc in chunks
    ]

    return {"retrieved_chunks": chunks, "sources": sources}


async def format_context_node(state: GraphState) -> dict[str, Any]:
    """Stitch retrieved chunks into a single string with `[SOURCE: ...]`
    labels. The labels let the LLM distinguish which project a chunk belongs
    to, which prevents it from attributing features across projects."""
    from app.services import retrieval

    context = retrieval._format_context(state["retrieved_chunks"])
    return {"context": context}


async def generate_answer_node(state: GraphState) -> dict[str, Any]:
    """Call the LLM with system prompt + history + retrieved context.

    Uses chain.astream() internally so that:
      - graph.ainvoke() still gets a full answer (we accumulate chunks here)
      - graph.astream_events() sees on_chat_model_stream events per token,
        which stream_query() re-emits as SSE tokens — with zero extra wiring.

    Rate-limit fallback (70B → 8B) lives here; it stays a local try/except
    because it's an error-recovery concern, not a pipeline branch.
    """
    from app.services import retrieval

    prompt = ChatPromptTemplate.from_messages([
        ("system", retrieval.SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ])

    lc_history = []
    for msg in state.get("history", []):
        if msg.role == "user":
            lc_history.append(HumanMessage(content=msg.content))
        else:
            lc_history.append(AIMessage(content=msg.content))

    params = {
        "context": state["context"],
        "history": lc_history,
        "question": state["question"],
    }

    async def _astream_collect(llm) -> str:
        chain = prompt | llm
        buf = ""
        async for chunk in chain.astream(params):
            if chunk.content:
                buf += chunk.content
        return buf

    try:
        answer = await _astream_collect(retrieval._get_llm())
    except Exception as e:
        if retrieval._is_rate_limit_error(e):
            logger.warning(
                "Primary model rate-limited, falling back to %s: %s",
                retrieval.FALLBACK_MODEL, str(e)[:200],
            )
            answer = await _astream_collect(
                retrieval._get_llm(retrieval.FALLBACK_MODEL)
            )
        else:
            raise

    return {"answer": answer}


async def generate_followups_node(state: GraphState) -> dict[str, Any]:
    """Three short follow-up questions a recruiter might ask next. Best-effort:
    failures return an empty list and don't block the main answer."""
    from app.services import retrieval

    follow_ups = retrieval._generate_followups(state["question"], state["answer"])
    return {"follow_ups": follow_ups}


def _evaluate_confidence(
    chunks: list[dict],
    *,
    threshold_hi: float,
    threshold_mid: float,
    min_chunks: int,
) -> tuple[str, str]:
    """Classify a retrieval result as "high" or "low" confidence.

    Pure function — no state, no I/O — so tests can exercise every branch
    without spinning up the graph.

    Low confidence if ANY of:
      1. No chunks at all.
      2. Top score is below the strong cutoff (threshold_hi).
      3. Fewer than min_chunks were returned AND the top score is below
         the weaker cutoff (threshold_mid) — i.e. thin results AND not
         overwhelmingly relevant.
    """
    if not chunks:
        return "low", "no chunks returned"

    scores = [c.get("score", 0.0) for c in chunks]
    max_score = max(scores) if scores else 0.0

    if max_score < threshold_hi:
        return (
            "low",
            f"max score {max_score:.4f} < threshold_hi {threshold_hi}",
        )

    if len(chunks) < min_chunks and max_score < threshold_mid:
        return (
            "low",
            f"only {len(chunks)} chunks and max score {max_score:.4f} "
            f"< threshold_mid {threshold_mid}",
        )

    return (
        "high",
        f"{len(chunks)} chunks, max score {max_score:.4f}",
    )


async def evaluate_retrieval_node(state: GraphState) -> dict[str, Any]:
    """Gate between retrieval and generation. Writes the confidence verdict
    to state so the conditional edge can route to fallback_response without
    the LLM ever seeing weak context."""
    chunks = state.get("retrieved_chunks", []) or []
    confidence, reason = _evaluate_confidence(
        chunks,
        threshold_hi=settings.rag_threshold_hi,
        threshold_mid=settings.rag_threshold_mid,
        min_chunks=settings.rag_min_chunks,
    )
    logger.info(
        "Retrieval confidence=%s | reason=%s | question=%r",
        confidence, reason, state.get("question", "")[:80],
    )
    return {"confidence": confidence, "confidence_reason": reason}


async def fallback_response_node(state: GraphState) -> dict[str, Any]:
    """Low-confidence retrieval (empty, weak, or too-few chunks). Return a
    friendly suggestion rather than letting the LLM hallucinate over the
    irrelevant chunks it would otherwise be handed."""
    return {
        "answer": (
            "I couldn't find any relevant information about that topic. "
            "Try asking about Tiago's projects (Odys, Inspection API, RAG Chatbot), "
            "his experience, or his tech stack."
        ),
        "sources": [],
        "follow_ups": [],
    }


# ─── Conditional edge ──────────────────────────────────────────────────────

def _route_after_evaluate(state: GraphState) -> str:
    """Dispatch based on the confidence verdict written by evaluate_retrieval."""
    if state.get("confidence") == "low":
        return "fallback_response"
    return "format_context"


# ─── Graph assembly ────────────────────────────────────────────────────────

def build_graph():
    """Assemble and compile the StateGraph. Called once at import time."""
    builder = StateGraph(GraphState)

    builder.add_node("enrich_query", enrich_query_node)
    builder.add_node("route_query", route_query_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("evaluate_retrieval", evaluate_retrieval_node)
    builder.add_node("format_context", format_context_node)
    builder.add_node("generate_answer", generate_answer_node)
    builder.add_node("generate_followups", generate_followups_node)
    builder.add_node("fallback_response", fallback_response_node)

    builder.add_edge(START, "enrich_query")
    builder.add_edge("enrich_query", "route_query")
    builder.add_edge("route_query", "retrieve")
    builder.add_edge("retrieve", "evaluate_retrieval")
    builder.add_conditional_edges(
        "evaluate_retrieval",
        _route_after_evaluate,
        {
            "format_context": "format_context",
            "fallback_response": "fallback_response",
        },
    )
    builder.add_edge("format_context", "generate_answer")
    builder.add_edge("generate_answer", "generate_followups")
    builder.add_edge("generate_followups", END)
    builder.add_edge("fallback_response", END)

    return builder.compile()


# Module-level singleton — compiled once per process.
graph = build_graph()
