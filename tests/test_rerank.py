"""Tests for the cross-encoder rerank node in graph.py.

We mock the cross-encoder to avoid downloading ~80MB of ONNX weights in CI.
Two scenarios cover the gate's branches end-to-end:

  1. High rerank score → evaluate_retrieval routes to format_context.
  2. Low rerank score  → evaluate_retrieval routes to fallback_response.
"""

import asyncio
from unittest.mock import patch

import pytest

from app.services.graph import rerank_node, evaluate_retrieval_node


def _chunk(text: str) -> dict:
    """Minimal RRF-output shape the rerank node expects."""
    return {"content": text, "metadata": {"filename": "knowledge_base.md"}}


class FakeReranker:
    """Stand-in for fastembed's TextCrossEncoder. Returns logits from an
    injected map so tests can dial relevance up or down at will."""

    def __init__(self, logit_map):
        # Map from chunk content → raw logit (pre-sigmoid).
        self.logit_map = logit_map

    def rerank(self, query, documents):
        return [self.logit_map[doc] for doc in documents]


@pytest.fixture
def mock_high_relevance():
    # +3 logit → sigmoid ≈ 0.95, well above the 0.3 min_score
    fake = FakeReranker({
        "python is a programming language": 3.0,
        "fastapi is a python web framework": 2.5,
        "unrelated chunk about weather": -8.0,
    })
    with patch("app.services.retrieval._get_reranker", return_value=fake):
        yield


@pytest.fixture
def mock_low_relevance():
    # All strongly negative → every sigmoid score well under 0.3
    fake = FakeReranker({
        "chunk one": -9.0,
        "chunk two": -10.0,
        "chunk three": -11.0,
    })
    with patch("app.services.retrieval._get_reranker", return_value=fake):
        yield


def test_rerank_node_high_relevance_routes_to_format_context(mock_high_relevance):
    state = {
        "search_query": "what is python",
        "retrieved_chunks": [
            _chunk("python is a programming language"),
            _chunk("fastapi is a python web framework"),
            _chunk("unrelated chunk about weather"),
        ],
    }

    rerank_out = asyncio.run(rerank_node(state))
    assert rerank_out["reranked_chunks"][0]["content"] == "python is a programming language"
    assert rerank_out["max_rerank_score"] > 0.9  # sigmoid(3) ≈ 0.95
    assert len(rerank_out["sources"]) == len(rerank_out["reranked_chunks"])

    eval_state = {**state, **rerank_out}
    eval_out = asyncio.run(evaluate_retrieval_node(eval_state))
    assert eval_out["confidence"] == "high"


def test_rerank_node_low_relevance_routes_to_fallback(mock_low_relevance):
    state = {
        "search_query": "what is the weather in tokyo",
        "retrieved_chunks": [
            _chunk("chunk one"),
            _chunk("chunk two"),
            _chunk("chunk three"),
        ],
    }

    rerank_out = asyncio.run(rerank_node(state))
    # Even the "best" chunk should sigmoid-normalise well below 0.3
    assert rerank_out["max_rerank_score"] < 0.1

    eval_state = {**state, **rerank_out}
    eval_out = asyncio.run(evaluate_retrieval_node(eval_state))
    assert eval_out["confidence"] == "low"
    assert "min_score" in eval_out["confidence_reason"]


def test_rerank_node_empty_input_gives_zero_score():
    """If retrieve returned nothing, rerank should cleanly return empty
    state rather than blowing up trying to call the cross-encoder."""
    state = {"search_query": "q", "retrieved_chunks": []}
    out = asyncio.run(rerank_node(state))
    assert out["reranked_chunks"] == []
    assert out["max_rerank_score"] == 0.0
    assert out["sources"] == []
