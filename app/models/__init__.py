"""
app/models/ — Data Models Layer

Defines the shape of data flowing through the application using Pydantic.

    schemas.py contains:
        QueryRequest    → What the frontend sends: {question, document_id, history}
        QueryResponse   → What the API returns: {answer, sources}
        ChatMessage     → A single message in conversation history: {role, content}
        Source          → A retrieved chunk reference: {content, page, section, document_id}
        UploadResponse  → After PDF upload: {document_id, filename, chunks_count}
        DocumentInfo    → Document listing: {document_id, filename}

Why Pydantic:
    - Automatic validation (rejects bad requests with clear error messages)
    - Automatic JSON serialization (Python objects → JSON responses)
    - Auto-generates OpenAPI/Swagger documentation at /docs
    - Type safety — IDE catches errors before runtime
"""
