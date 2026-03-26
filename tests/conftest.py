import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_pdf_bytes():
    """Minimal valid PDF for upload tests."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (Hello World) Tj ET\n"
        b"endstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f\n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n0\n%%EOF"
    )


@pytest.fixture
def mock_ingest():
    """Mock ingestion so tests don't need ChromaDB or embeddings."""
    with patch("app.api.routes.ingestion.ingest_pdf", return_value=("test-doc-id", 5)):
        yield


@pytest.fixture
def mock_query():
    """Mock retrieval so tests don't need ChromaDB or Groq."""
    from app.models.schemas import QueryResponse, Source
    mock_response = QueryResponse(
        answer="Tiago is a backend developer with Python and FastAPI experience.",
        sources=[Source(content="Python | FastAPI", page=1, section="Skills", document_id="test-doc-id")],
    )
    with patch("app.api.routes.retrieval.query", return_value=mock_response):
        yield
