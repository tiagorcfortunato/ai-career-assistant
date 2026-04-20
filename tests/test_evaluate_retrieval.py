"""Tests for the low-confidence retrieval gate in graph.py.

The gate now fires on cross-encoder rerank scores (sigmoid-normalised to
[0, 1]) rather than RRF position scores. We exercise the pure helper
`_evaluate_confidence` directly — it takes scores as arguments, so testing
it is independent of the cross-encoder, ChromaDB, Groq, and the graph
itself. If this function is right, the node that wraps it is trivially
right.
"""

import pytest

from app.services.graph import _evaluate_confidence


MIN_SCORE = 0.3  # match the design brief default


def _chunk(rerank_score: float) -> dict:
    """Build a minimal chunk dict mirroring what rerank_node writes."""
    return {"content": "x", "metadata": {}, "rerank_score": rerank_score}


def test_empty_chunks_is_low_confidence():
    confidence, reason = _evaluate_confidence([], 0.0, min_score=MIN_SCORE)
    assert confidence == "low"
    assert "no chunks" in reason


def test_weak_top_score_is_low_confidence():
    """Cross-encoder is confident nothing is relevant (all scores ~0.05)."""
    chunks = [_chunk(0.05), _chunk(0.03), _chunk(0.01)]
    confidence, reason = _evaluate_confidence(chunks, 0.05, min_score=MIN_SCORE)
    assert confidence == "low"
    assert "min_score" in reason


def test_strong_top_score_is_high_confidence():
    """Happy path — a chunk scored clearly above the threshold."""
    chunks = [_chunk(0.82), _chunk(0.45), _chunk(0.31)]
    confidence, reason = _evaluate_confidence(chunks, 0.82, min_score=MIN_SCORE)
    assert confidence == "high"
    assert "3 chunks" in reason


def test_score_exactly_at_threshold_is_high():
    """Threshold is a strict *less than*, so meeting it counts as high."""
    chunks = [_chunk(MIN_SCORE)]
    confidence, _ = _evaluate_confidence(chunks, MIN_SCORE, min_score=MIN_SCORE)
    assert confidence == "high"


def test_score_just_below_threshold_is_low():
    chunks = [_chunk(0.299)]
    confidence, _ = _evaluate_confidence(chunks, 0.299, min_score=MIN_SCORE)
    assert confidence == "low"


def test_single_strong_chunk_is_high_confidence():
    """One very-relevant chunk is enough — the old `min_chunks` signal is gone
    because the cross-encoder's score already encodes confidence."""
    chunks = [_chunk(0.9)]
    confidence, _ = _evaluate_confidence(chunks, 0.9, min_score=MIN_SCORE)
    assert confidence == "high"


@pytest.mark.parametrize("score", [0.0, 0.15, 0.29])
def test_below_threshold_is_low(score):
    chunks = [_chunk(score), _chunk(score / 2)]
    confidence, _ = _evaluate_confidence(chunks, score, min_score=MIN_SCORE)
    assert confidence == "low"


@pytest.mark.parametrize("score", [0.3, 0.55, 0.99])
def test_above_threshold_is_high(score):
    chunks = [_chunk(score)]
    confidence, _ = _evaluate_confidence(chunks, score, min_score=MIN_SCORE)
    assert confidence == "high"
