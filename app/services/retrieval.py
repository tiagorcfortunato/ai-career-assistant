"""
app/services/retrieval.py — RAG Query Pipeline (the "brain")

This is where the core RAG logic lives. When a user asks a question:

1. ENRICH: If the query is short (<5 words), prepend conversation history
   to resolve follow-up references like "tell me more about that"
2. RETRIEVE (Hybrid): Run both semantic search (ChromaDB) AND keyword search (BM25),
   then fuse results using Reciprocal Rank Fusion (RRF) for best-of-both-worlds retrieval
3. GENERATE: Send system prompt + conversation history + retrieved chunks + question
   to the Groq LLM (Llama 3.1 8B Instant)
4. RETURN: Either as a full JSON response (query) or as streaming SSE tokens (stream_query)

Key design decisions:
- Hybrid search combines semantic understanding with exact keyword matching
- RRF fusion doesn't need tuning — it's parameter-free and robust
- History enrichment only for short queries (prevents context pollution on specific questions)
- Simple single-pass retrieval (no query expansion) to minimize latency and noise
- System prompt allows rephrasing but anchors all factual claims to retrieved context
"""

import json
import re
from typing import AsyncGenerator

from langchain_groq import ChatGroq
from langchain_chroma import Chroma
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from rank_bm25 import BM25Okapi

from app.config import settings
from app.models.schemas import ChatMessage, QueryResponse, Source
from app.services.embeddings import FastEmbeddings


SYSTEM_PROMPT = """You are the Professional Talent Assistant for Tiago Fortunato, a Software Engineer specialized in AI and Backend based in Berlin. Your goal is to help recruiters, hiring managers, and technical interviewers understand Tiago's technical depth and professional journey.

Rules:
- You may rephrase, restructure, and improve the clarity of information from the context. Sound natural and professional, not robotic.
- However, every FACTUAL CLAIM must be grounded in the context. You may say things differently, but you must not invent facts, metrics, outcomes, or achievements that are not in the context. For example: if the context says "live in production but no meaningful user traction yet", do NOT say "strong user base" or "proven track record of scalability".
- If the context does not contain enough information to fully answer the question, clearly state what you know from the context and what you don't. NEVER fill gaps with assumptions or general knowledge. Saying "I don't have that specific information" is better than guessing.
- Do NOT add generic advice, industry best practices, or common knowledge that is not in the context. Every sentence in your response should be traceable to a specific part of the context.
- ALWAYS respond in English by default. Only switch to another language if the user explicitly writes their question in that language (Portuguese, German, etc.).
- The context chunks may be labeled with subsection titles — they all pertain to Tiago's profile.
- If you genuinely don't have the information, say so briefly and pivot to a related strength Tiago does have. You may suggest follow-up questions, but ONLY ones that highlight Tiago's strengths.
- Emphasize the Inspection Management API and the RAG Chatbot as core technical proofs of his work.
- When mentioning URLs or GitHub links, ALWAYS format them as markdown links: [display text](https://full-url). Never write raw URLs as plain text.
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
) -> list[dict]:
    """
    Combines semantic search (ChromaDB) and keyword search (BM25) using
    Reciprocal Rank Fusion (RRF). This captures both meaning-based and
    exact-keyword matches — e.g., "FastAPI" matches even if the embedding
    doesn't capture the exact term well.

    RRF formula: score = sum(1 / (rank + 60)) across all result lists.
    The constant 60 is standard (from the original RRF paper).
    """
    vector_store = _get_vector_store()
    search_filter = {"document_id": document_id} if document_id else None

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

    # 4. Sort by fused score and return top-k
    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[key] for key, _ in ranked[:k]]


# ─── Vector store ────────────────────────────────────────────────────────────

def _get_vector_store() -> Chroma:
    embeddings = FastEmbeddings(model_name=settings.embedding_model)
    return Chroma(
        persist_directory=settings.chroma_path,
        embedding_function=embeddings,
    )


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


def query(question: str, document_id: str | None, history: list[ChatMessage]) -> QueryResponse:
    """
    Hybrid search (semantic + BM25) for relevant chunks, then asks the LLM
    to answer taking conversation history into account.
    """
    # 1. Enrich query with history context for better retrieval
    search_query = _build_search_query(question, history)

    # 2. Hybrid search: semantic + BM25 with RRF fusion
    results = _hybrid_search(search_query, document_id, k=settings.retrieval_k)

    if not results:
        return QueryResponse(
            answer="I couldn't find any relevant information in the uploaded documents.",
            sources=[],
        )

    # 3. Build context string from retrieved chunks
    context = "\n\n---\n\n".join([doc["content"] for doc in results])

    # 4. Build prompt with history support
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ])

    llm = ChatGroq(
        model=settings.llm_model,
        api_key=settings.groq_api_key,
        temperature=0,
    )
    chain = prompt | llm

    # 5. Convert history to LangChain message objects
    lc_history = []
    for msg in history:
        if msg.role == "user":
            lc_history.append(HumanMessage(content=msg.content))
        else:
            lc_history.append(AIMessage(content=msg.content))

    response = chain.invoke({
        "context": context,
        "history": lc_history,
        "question": question,
    })

    # 6. Build sources
    sources = [
        Source(
            content=doc["content"][:200],
            page=doc["metadata"].get("page", 0),
            section=doc["metadata"].get("section", ""),
            document_id=doc["metadata"].get("document_id", ""),
        )
        for doc in results
    ]

    return QueryResponse(answer=response.content, sources=sources)


async def stream_query(
    question: str, document_id: str | None, history: list[ChatMessage]
) -> AsyncGenerator[str, None]:
    """Streaming version of query() — yields SSE-formatted lines."""

    search_query = _build_search_query(question, history)
    results = _hybrid_search(search_query, document_id, k=settings.retrieval_k)

    if not results:
        yield f"data: {json.dumps({'token': 'I could not find relevant information about that topic.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    context = "\n\n---\n\n".join([doc["content"] for doc in results])

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ])

    llm = ChatGroq(model=settings.llm_model, api_key=settings.groq_api_key, temperature=0)
    chain = prompt | llm

    lc_history = []
    for msg in history:
        if msg.role == "user":
            lc_history.append(HumanMessage(content=msg.content))
        else:
            lc_history.append(AIMessage(content=msg.content))

    sources = [
        {"section": doc["metadata"].get("section", ""), "page": doc["metadata"].get("page", 0)}
        for doc in results
    ]
    yield f"data: {json.dumps({'sources': sources})}\n\n"

    async for chunk in chain.astream({
        "context": context,
        "history": lc_history,
        "question": question,
    }):
        if chunk.content:
            yield f"data: {json.dumps({'token': chunk.content})}\n\n"

    yield "data: [DONE]\n\n"
