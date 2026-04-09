"""
app/services/ingestion.py — Document Ingestion Pipeline (the "librarian")

Handles reading documents (PDFs or Markdown), splitting them into meaningful chunks,
embedding them as vectors, and storing them in ChromaDB.

Two ingestion paths:
  ingest_pdf()      → For PDFs: uses PyMuPDF font-size analysis to detect headings,
                      groups text under headings, splits large sections with RecursiveCharacterTextSplitter
  ingest_markdown() → For Markdown: splits by ATX headings (# ## ###), same adaptive chunking

Key design decision — section-aware chunking:
  Naive fixed-size chunking (every 500 chars) breaks sentences and loses context.
  Instead, we detect document structure (headings) and keep sections whole when possible.
  Each sub-chunk is prefixed with its section title so the retriever knows the context.

Chunk parameters: chunk_size=500, chunk_overlap=50
  - 500 chars ≈ 150 words — enough for a coherent paragraph
  - 50 char overlap prevents losing info at chunk boundaries
  - Any "overview" section must fit within 500 chars or it gets split (defeating its purpose)
"""

import uuid
from pathlib import Path

import fitz  # PyMuPDF
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

from app.config import settings
from app.services.embeddings import FastEmbeddings


def _get_vector_store() -> Chroma:
    embeddings = FastEmbeddings(model_name=settings.embedding_model)
    return Chroma(
        persist_directory=settings.chroma_path,
        embedding_function=embeddings,
    )


def ingest_markdown(file_path: Path, filename: str) -> tuple[str, int]:
    """
    Reads a Markdown file, splits into heading-aware chunks, embeds and stores in ChromaDB.
    Returns (document_id, chunks_count).
    """
    document_id = str(uuid.uuid4())
    text = file_path.read_text(encoding="utf-8")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    sections = _extract_markdown_sections(text)
    chunks = []
    metadatas = []

    for section_title, section_text in sections:
        if len(section_text) <= settings.chunk_size:
            chunks.append(section_text)
            metadatas.append({
                "document_id": document_id,
                "filename": filename,
                "page": 1,
                "section": section_title,
            })
        else:
            sub_chunks = splitter.split_text(section_text)
            for sub_chunk in sub_chunks:
                chunks.append(f"{section_title}\n{sub_chunk}")
                metadatas.append({
                    "document_id": document_id,
                    "filename": filename,
                    "page": 1,
                    "section": section_title,
                })

    vector_store = _get_vector_store()
    vector_store.add_texts(texts=chunks, metadatas=metadatas)

    return document_id, len(chunks)


def _extract_markdown_sections(text: str) -> list[tuple[str, str]]:
    """
    Splits markdown text into sections by ATX headings (# ## ###).
    Returns list of (section_title, section_text).
    """
    sections = []
    current_title = "Introduction"
    current_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_lines:
                sections.append((current_title, current_title + "\n" + "\n".join(current_lines)))
            current_title = stripped.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_title + "\n" + "\n".join(current_lines)))

    return sections if sections else [("Document", text)]


def ingest_pdf(file_path: Path, filename: str) -> tuple[str, int]:
    """
    Reads a PDF, splits into section-aware chunks, embeds and stores in ChromaDB.
    Returns (document_id, chunks_count).
    """
    document_id = str(uuid.uuid4())

    # 1. Extract sections using font-size-based heading detection
    sections = _extract_sections(file_path)

    # 2. Fallback splitter for sections that are too long
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    chunks = []
    metadatas = []

    for section_title, section_text, page_num in sections:
        # If section fits in one chunk, keep it whole
        if len(section_text) <= settings.chunk_size:
            chunks.append(section_text)
            metadatas.append({
                "document_id": document_id,
                "filename": filename,
                "page": page_num,
                "section": section_title,
            })
        else:
            # Split large sections but prefix each sub-chunk with the section title
            sub_chunks = splitter.split_text(section_text)
            for sub_chunk in sub_chunks:
                chunks.append(f"{section_title}\n{sub_chunk}")
                metadatas.append({
                    "document_id": document_id,
                    "filename": filename,
                    "page": page_num,
                    "section": section_title,
                })

    # 3. Store in ChromaDB
    vector_store = _get_vector_store()
    vector_store.add_texts(texts=chunks, metadatas=metadatas)

    return document_id, len(chunks)


def _extract_sections(file_path: Path) -> list[tuple[str, str, int]]:
    """
    Detects section headings by font size and groups content under each heading.
    Returns list of (section_title, section_text, page_number).
    """
    sections = []
    current_title = "Introduction"
    current_lines = []
    current_page = 1

    with fitz.open(str(file_path)) as doc:
        # First pass: find the median font size to use as heading threshold
        all_sizes = []
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        if span["text"].strip():
                            all_sizes.append(span["size"])

        if not all_sizes:
            return [("Document", "", 1)]

        median_size = sorted(all_sizes)[len(all_sizes) // 2]
        heading_threshold = median_size * 1.15  # 15% larger than median = heading

        # Second pass: split by headings
        for page_num, page in enumerate(doc, start=1):
            for block in page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    line_text = " ".join(s["text"] for s in line["spans"]).strip()
                    if not line_text:
                        continue

                    max_size = max(s["size"] for s in line["spans"])
                    is_heading = (
                        max_size >= heading_threshold
                        and len(line_text) < 60  # headings are short
                    )

                    if is_heading:
                        # Save previous section
                        if current_lines:
                            sections.append((
                                current_title,
                                current_title + "\n" + "\n".join(current_lines),
                                current_page,
                            ))
                        current_title = line_text
                        current_lines = []
                        current_page = page_num
                    else:
                        current_lines.append(line_text)

    # Save last section
    if current_lines:
        sections.append((
            current_title,
            current_title + "\n" + "\n".join(current_lines),
            current_page,
        ))

    return sections if sections else [("Document", "", 1)]
