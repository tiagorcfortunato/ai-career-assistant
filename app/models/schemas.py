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
