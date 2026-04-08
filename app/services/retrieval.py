import json
from typing import AsyncGenerator

from langchain_groq import ChatGroq
from langchain_chroma import Chroma
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from app.config import settings
from app.models.schemas import ChatMessage, QueryResponse, Source
from app.services.embeddings import FastEmbeddings


SYSTEM_PROMPT = """You are the Professional Talent Assistant for Tiago Fortunato, a Software Engineer specialized in AI and Backend based in Berlin. Your goal is to help recruiters understand Tiago's technical journey and expertise.

Rules:
- Answer in a professional, technical, and concise manner.
- Primary language is English. If the user asks in another language (like Portuguese or German), respond in that language.
- The context below contains comprehensive information about Tiago. Context chunks may be labeled with subsection titles (e.g. "Key Technical Details", "Proposed Solution") — they all pertain to Tiago's profile. Always answer from the provided context.
- When you have relevant context, use it fully to give a thorough answer. Do not say you lack information if the context contains relevant details.
- Never hallucinate or invent experiences not present in the context.
- Emphasize the Inspection Management API and the RAG Chatbot as core technical proofs of his work.

Context:
{context}"""


def _get_vector_store() -> Chroma:
    embeddings = FastEmbeddings(model_name=settings.embedding_model)
    return Chroma(
        persist_directory=settings.chroma_path,
        embedding_function=embeddings,
    )


def _build_search_query(question: str, history: list[ChatMessage]) -> str:
    """
    If there's conversation history, enrich the search query with recent context.
    This helps resolve references like "tell me more about the first one".
    """
    if not history:
        return question
    last_exchange = history[-2:] if len(history) >= 2 else history
    context = " ".join(m.content for m in last_exchange)
    return f"{context} {question}"


def query(question: str, document_id: str | None, history: list[ChatMessage]) -> QueryResponse:
    """
    Searches ChromaDB for relevant chunks, then asks the LLM to answer
    taking conversation history into account.
    """
    vector_store = _get_vector_store()

    # 1. Enrich query with history context for better retrieval
    search_query = _build_search_query(question, history)
    search_filter = {"document_id": document_id} if document_id else None

    # 2. Similarity search
    results = vector_store.similarity_search(
        query=search_query,
        k=settings.retrieval_k,
        filter=search_filter,
    )

    if not results:
        return QueryResponse(
            answer="I couldn't find any relevant information in the uploaded documents.",
            sources=[],
        )

    # 3. Build context string from retrieved chunks
    context = "\n\n---\n\n".join([doc.page_content for doc in results])

    # 4. Build prompt with history support
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ])

    llm = ChatGroq(
        model=settings.llm_model,
        api_key=settings.groq_api_key,
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
            content=doc.page_content[:200],
            page=doc.metadata.get("page", 0),
            section=doc.metadata.get("section", ""),
            document_id=doc.metadata.get("document_id", ""),
        )
        for doc in results
    ]

    return QueryResponse(answer=response.content, sources=sources)


async def stream_query(
    question: str, document_id: str | None, history: list[ChatMessage]
) -> AsyncGenerator[str, None]:
    """Streaming version of query() — yields SSE-formatted lines."""
    vector_store = _get_vector_store()

    search_query = _build_search_query(question, history)
    search_filter = {"document_id": document_id} if document_id else None

    results = vector_store.similarity_search(
        query=search_query,
        k=settings.retrieval_k,
        filter=search_filter,
    )

    if not results:
        yield f"data: {json.dumps({'token': 'I could not find relevant information about that topic.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    context = "\n\n---\n\n".join([doc.page_content for doc in results])

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ])

    llm = ChatGroq(model=settings.llm_model, api_key=settings.groq_api_key)
    chain = prompt | llm

    lc_history = []
    for msg in history:
        if msg.role == "user":
            lc_history.append(HumanMessage(content=msg.content))
        else:
            lc_history.append(AIMessage(content=msg.content))

    sources = [
        {"section": doc.metadata.get("section", ""), "page": doc.metadata.get("page", 0)}
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
