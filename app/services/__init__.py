"""
app/services/ — Business Logic Layer

This is where the actual work happens. Three services:

    retrieval.py   → The RAG query pipeline
                     Takes a question → retrieves relevant chunks → asks the LLM → returns answer
                     Supports both full response (query) and streaming (stream_query)

    ingestion.py   → The document processing pipeline
                     Takes a file → detects sections → splits into chunks → embeds → stores in ChromaDB
                     Supports PDFs (font-size heading detection) and Markdown (ATX headings)

    embeddings.py  → The embedding model wrapper
                     Converts text → 384-dimensional vectors using BAAI/bge-small-en-v1.5
                     Runs locally on CPU via fastembed (no API calls, zero cost)

Services are independent of HTTP — they don't know about requests or responses.
They receive Python objects and return Python objects. This makes them testable
and reusable (e.g., the same retrieval.py works for both API and RAGAS evaluation).
"""
