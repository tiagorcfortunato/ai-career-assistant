import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_PATH = Path("data/knowledge_base.md")


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
