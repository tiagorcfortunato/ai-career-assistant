"""
app/ — RAG Career Chatbot Application

Layered architecture (same pattern as the Inspection Management API):

    ┌─────────────────────────────────────────────────────┐
    │  main.py          → App entry point, startup logic  │
    ├─────────────────────────────────────────────────────┤
    │  api/routes.py    → HTTP endpoints (the "waiter")   │
    │                     Receives requests, returns JSON  │
    ├─────────────────────────────────────────────────────┤
    │  services/         → Business logic (the "brain")   │
    │    retrieval.py    → RAG query pipeline + streaming  │
    │    ingestion.py    → Document chunking + embedding   │
    │    embeddings.py   → Local embedding model wrapper   │
    ├─────────────────────────────────────────────────────┤
    │  models/schemas.py → Data shapes (the "contract")   │
    │                     Pydantic request/response models │
    ├─────────────────────────────────────────────────────┤
    │  config.py         → Settings from environment vars │
    ├─────────────────────────────────────────────────────┤
    │  static/index.html → Frontend (chat UI)             │
    └─────────────────────────────────────────────────────┘

Data flow:
    User question → routes.py → retrieval.py → ChromaDB + Groq LLM → SSE stream → Frontend

Why this structure:
    - Each layer has ONE responsibility (Single Responsibility Principle)
    - routes.py never touches ChromaDB directly — it calls services
    - services never handle HTTP concerns — they return data, not responses
    - schemas.py defines the contract between frontend and backend
    - Easy to test: mock services to test routes, mock ChromaDB to test services
"""
