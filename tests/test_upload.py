import io


def test_upload_pdf_success(client, sample_pdf_bytes, mock_ingest):
    response = client.post(
        "/api/upload",
        files={"file": ("test.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == "test-doc-id"
    assert data["filename"] == "test.pdf"
    assert data["chunks_count"] == 5


def test_upload_non_pdf_rejected(client):
    response = client.post(
        "/api/upload",
        files={"file": ("report.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_upload_missing_file(client):
    response = client.post("/api/upload")
    assert response.status_code == 422
