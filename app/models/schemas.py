"""
app/models/schemas.py — Request/Response Data Shapes (the "contract")

Defines the exact structure of every request and response using Pydantic models.
FastAPI uses these to:
  1. Validate incoming requests (reject malformed data with 422 errors)
  2. Serialize outgoing responses (convert Python objects to JSON)
  3. Auto-generate OpenAPI/Swagger docs at /docs

This is the same pattern used in the Inspection Management API —
clean separation between HTTP layer (routes) and data validation (schemas).
"""

from pydantic import BaseModel


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    chunks_count: int


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class QueryRequest(BaseModel):
    question: str
    document_id: str | None = None
    history: list[ChatMessage] = []


class Source(BaseModel):
    content: str
    page: int
    section: str
    document_id: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
