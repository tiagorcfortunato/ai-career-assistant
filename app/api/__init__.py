"""
app/api/ — HTTP API Layer

This layer handles all HTTP concerns: receiving requests, validating input,
calling the right service, and formatting responses.

It does NOT contain business logic — that lives in app/services/.

This separation means:
    - You can change how the API responds (e.g., add a new endpoint)
      without touching the RAG pipeline
    - You can test the RAG pipeline without running an HTTP server
    - The API is a thin wrapper that translates HTTP ↔ Python function calls
"""
