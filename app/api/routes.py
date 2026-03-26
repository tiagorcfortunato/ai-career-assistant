import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.models.schemas import UploadResponse, QueryRequest, QueryResponse, DocumentInfo
from app.services import ingestion, retrieval
from app.config import settings

router = APIRouter()

DATA_DIR = Path("data")


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    DATA_DIR.mkdir(exist_ok=True)
    file_path = DATA_DIR / file.filename

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    document_id, chunks_count = ingestion.ingest_pdf(file_path, file.filename)

    return UploadResponse(
        document_id=document_id,
        filename=file.filename,
        chunks_count=chunks_count,
    )


@router.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    return retrieval.query(
        question=request.question,
        document_id=request.document_id,
        history=request.history,
    )


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents():
    from langchain_chroma import Chroma
    from app.services.embeddings import FastEmbeddings

    embeddings = FastEmbeddings(model_name=settings.embedding_model)
    vector_store = Chroma(
        persist_directory=settings.chroma_path,
        embedding_function=embeddings,
    )

    collection = vector_store.get()
    if not collection["metadatas"]:
        return []

    seen = {}
    for metadata in collection["metadatas"]:
        doc_id = metadata.get("document_id")
        if doc_id and doc_id not in seen:
            seen[doc_id] = metadata.get("filename", "unknown")

    return [
        DocumentInfo(document_id=doc_id, filename=filename)
        for doc_id, filename in seen.items()
    ]
