"""
app/main.py — Application Entry Point

This is where the FastAPI app is created and configured. It handles:
1. Lifespan: on startup, auto-ingests the knowledge base (if not already indexed)
2. Readiness: /health returns 503 while startup is running, 200 once ready
3. Middleware: CORS (allows cross-origin requests), static file serving
4. Routing: mounts the API router at /api and serves the frontend at /

Think of this as the "manager" — it wires everything together but doesn't do the actual work.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_PATH = Path("data/knowledge_base.md")
ODYS_KNOWLEDGE_PATH = Path("data/odys_knowledge.md")
RAG_KNOWLEDGE_PATH = Path("data/rag_chatbot_knowledge.md")
INSPECTION_KNOWLEDGE_PATH = Path("data/inspection_api_knowledge.md")

# Readiness flag — flipped to True once lifespan startup is complete.
# /health reads this to decide between 503 (starting) and 200 (ready).
_is_ready = False


def _is_already_ingested(filename: str) -> bool:
    """Check if a document with this filename is already stored in ChromaDB."""
    from app.services.ingestion import _get_vector_store
    vector_store = _get_vector_store()
    results = vector_store.get(where={"filename": filename}, limit=1)
    return len(results.get("ids", [])) > 0


def _ensure_ingested(path: Path, label: str) -> None:
    if not path.exists():
        logger.warning("%s knowledge base not found at '%s' — skipping.", label, path)
        return
    filename = path.name
    if _is_already_ingested(filename):
        logger.info("%s knowledge '%s' already indexed — skipping.", label, filename)
        return
    from app.services.ingestion import ingest_markdown
    doc_id, chunks = ingest_markdown(path, filename)
    logger.info(
        "%s knowledge loaded: '%s' → document_id=%s, chunks=%d",
        label, filename, doc_id, chunks,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    _is_ready = False
    try:
        _ensure_ingested(KNOWLEDGE_BASE_PATH, "Base")
        _ensure_ingested(ODYS_KNOWLEDGE_PATH, "Odys")
        _ensure_ingested(RAG_KNOWLEDGE_PATH, "RAG")
        _ensure_ingested(INSPECTION_KNOWLEDGE_PATH, "Inspection API")
        _is_ready = True
        logger.info("Lifespan startup complete — /health now returns 200.")
    except Exception:
        logger.exception("Lifespan startup failed — /health will keep returning 503.")
        raise
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
def health(response: Response):
    if not _is_ready:
        response.status_code = 503
        return {"status": "starting"}
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse("app/static/index.html")
