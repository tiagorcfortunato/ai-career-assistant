"""
app/main.py — Application Entry Point

This is where the FastAPI app is created and configured. It handles:
1. Lifespan: on startup, auto-ingests the knowledge base (if not already indexed)
2. Keep-alive: background task pings /health every 10 min to prevent Render free tier spin-down
3. Middleware: CORS (allows cross-origin requests), static file serving
4. Routing: mounts the API router at /api and serves the frontend at /

Think of this as the "manager" — it wires everything together but doesn't do the actual work.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_PATH = Path("data/knowledge_base.md")
ODYS_KNOWLEDGE_PATH = Path("data/odys_knowledge.md")
RAG_KNOWLEDGE_PATH = Path("data/rag_chatbot_knowledge.md")
INSPECTION_KNOWLEDGE_PATH = Path("data/inspection_api_knowledge.md")
# Thesis content is included in knowledge_base.md to avoid OOM on t3.micro


def _is_already_ingested(filename: str) -> bool:
    """Check if a document with this filename is already stored in ChromaDB."""
    from app.services.ingestion import _get_vector_store
    vector_store = _get_vector_store()
    results = vector_store.get(where={"filename": filename}, limit=1)
    return len(results.get("ids", [])) > 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    if KNOWLEDGE_BASE_PATH.exists():
        filename = KNOWLEDGE_BASE_PATH.name
        if _is_already_ingested(filename):
            logger.info("Knowledge base '%s' already indexed — skipping.", filename)
        else:
            from app.services.ingestion import ingest_markdown
            doc_id, chunks = ingest_markdown(KNOWLEDGE_BASE_PATH, filename)
            logger.info(
                "Knowledge base loaded: '%s' → document_id=%s, chunks=%d",
                filename, doc_id, chunks,
            )
    else:
        logger.warning("Knowledge base not found at '%s' — skipping auto-load.", KNOWLEDGE_BASE_PATH)

    # Auto-ingest Odys deep-dive knowledge base
    if ODYS_KNOWLEDGE_PATH.exists():
        odys_filename = ODYS_KNOWLEDGE_PATH.name
        if _is_already_ingested(odys_filename):
            logger.info("Odys knowledge '%s' already indexed — skipping.", odys_filename)
        else:
            from app.services.ingestion import ingest_markdown
            doc_id, chunks = ingest_markdown(ODYS_KNOWLEDGE_PATH, odys_filename)
            logger.info(
                "Odys knowledge loaded: '%s' → document_id=%s, chunks=%d",
                odys_filename, doc_id, chunks,
            )

    # Auto-ingest RAG chatbot deep-dive knowledge base
    if RAG_KNOWLEDGE_PATH.exists():
        rag_filename = RAG_KNOWLEDGE_PATH.name
        if _is_already_ingested(rag_filename):
            logger.info("RAG knowledge '%s' already indexed — skipping.", rag_filename)
        else:
            from app.services.ingestion import ingest_markdown
            doc_id, chunks = ingest_markdown(RAG_KNOWLEDGE_PATH, rag_filename)
            logger.info(
                "RAG knowledge loaded: '%s' → document_id=%s, chunks=%d",
                rag_filename, doc_id, chunks,
            )

    # Auto-ingest Inspection API deep-dive knowledge base
    if INSPECTION_KNOWLEDGE_PATH.exists():
        insp_filename = INSPECTION_KNOWLEDGE_PATH.name
        if _is_already_ingested(insp_filename):
            logger.info("Inspection API knowledge '%s' already indexed — skipping.", insp_filename)
        else:
            from app.services.ingestion import ingest_markdown
            doc_id, chunks = ingest_markdown(INSPECTION_KNOWLEDGE_PATH, insp_filename)
            logger.info(
                "Inspection API knowledge loaded: '%s' → document_id=%s, chunks=%d",
                insp_filename, doc_id, chunks,
            )

    # Keep-alive: ping self every 10 min so free Render instance doesn't spin down
    async def _keep_alive():
        await asyncio.sleep(30)  # wait for server to finish starting
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    await client.get("http://localhost:8000/health", timeout=10)
                except Exception:
                    pass
                await asyncio.sleep(600)  # every 10 minutes

    asyncio.create_task(_keep_alive())
    yield


app = FastAPI(
    title="RAG PDF Chatbot",
    description="Upload PDFs and ask questions about their content.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse("app/static/index.html")
