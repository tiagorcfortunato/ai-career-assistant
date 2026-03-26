def test_query_success(client, mock_query):
    response = client.post(
        "/api/query",
        json={
            "question": "What is Tiago's experience?",
            "document_id": "test-doc-id",
            "history": [],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "sources" in data
    assert len(data["answer"]) > 0


def test_query_with_history(client, mock_query):
    response = client.post(
        "/api/query",
        json={
            "question": "Tell me more about his skills.",
            "document_id": "test-doc-id",
            "history": [
                {"role": "user", "content": "What does Tiago do?"},
                {"role": "assistant", "content": "He is a backend developer."},
            ],
        },
    )
    assert response.status_code == 200


def test_query_all_documents(client, mock_query):
    """Querying without document_id should search across all documents."""
    response = client.post(
        "/api/query",
        json={"question": "What technologies are used?"},
    )
    assert response.status_code == 200


def test_query_empty_question(client):
    response = client.post(
        "/api/query",
        json={"question": "   ", "document_id": "test-doc-id"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Question cannot be empty."


def test_query_missing_question(client):
    response = client.post("/api/query", json={})
    assert response.status_code == 422
