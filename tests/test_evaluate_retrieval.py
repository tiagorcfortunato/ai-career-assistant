"""Tests for the low-confidence retrieval gate added in graph.py.

We exercise the pure helper `_evaluate_confidence` directly — it has no
state or I/O, so testing it is independent of ChromaDB, Groq, or the
rest of the graph. If this function is right, the node that wraps it
is trivially right.
"""

import pytest

from app.services.graph import _evaluate_confidence


# Sensible thresholds for tests. These live here rather than reading from
# settings so a user tweaking env vars can't accidentally break the tests.
HI = 0.3
MID = 0.5
MIN_CHUNKS = 2


def _chunk(score: float) -> dict:
    """Build a minimal chunk dict the helper will accept."""
    return {"content": "x", "metadata": {}, "score": score}


def test_empty_chunks_is_low_confidence():
    confidence, reason = _evaluate_confidence(
        [], threshold_hi=HI, threshold_mid=MID, min_chunks=MIN_CHUNKS,
    )
    assert confidence == "low"
    assert "no chunks" in reason


def test_max_score_below_hi_is_low_confidence():
    """Even with plenty of chunks, if the best one is weak, we don't trust it."""
    chunks = [_chunk(0.1), _chunk(0.05), _chunk(0.01)]
    confidence, reason = _evaluate_confidence(
        chunks, threshold_hi=HI, threshold_mid=MID, min_chunks=MIN_CHUNKS,
    )
    assert confidence == "low"
    assert "threshold_hi" in reason


def test_too_few_chunks_and_weak_is_low_confidence():
    """A single chunk scoring 0.4 beats HI but is below MID and below min_chunks."""
    chunks = [_chunk(0.4)]
    confidence, reason = _evaluate_confidence(
        chunks, threshold_hi=HI, threshold_mid=MID, min_chunks=MIN_CHUNKS,
    )
    assert confidence == "low"
    assert "threshold_mid" in reason


def test_good_signals_is_high_confidence():
    """Enough chunks, top one above HI — this is the happy path."""
    chunks = [_chunk(0.7), _chunk(0.5), _chunk(0.35)]
    confidence, reason = _evaluate_confidence(
        chunks, threshold_hi=HI, threshold_mid=MID, min_chunks=MIN_CHUNKS,
    )
    assert confidence == "high"
    assert "3 chunks" in reason


def test_single_strong_chunk_is_high_confidence():
    """One chunk is below min_chunks, but if it scores above MID it's still
    a strong enough signal — the too-few branch only fires when BOTH
    conditions hold."""
    chunks = [_chunk(0.8)]
    confidence, _ = _evaluate_confidence(
        chunks, threshold_hi=HI, threshold_mid=MID, min_chunks=MIN_CHUNKS,
    )
    assert confidence == "high"


def test_missing_score_treated_as_zero():
    """A chunk without a score field shouldn't crash the evaluator — treat
    the absence as score=0 so missing-score chunks are conservatively low."""
    chunks = [{"content": "x", "metadata": {}}]  # no score field
    confidence, _ = _evaluate_confidence(
        chunks, threshold_hi=HI, threshold_mid=MID, min_chunks=MIN_CHUNKS,
    )
    assert confidence == "low"


@pytest.mark.parametrize("score", [0.29, 0.0, -0.1])
def test_below_hi_boundary_is_low(score):
    """Edge cases around the HI threshold — anything strictly below is low."""
    confidence, _ = _evaluate_confidence(
        [_chunk(score), _chunk(score)],
        threshold_hi=HI, threshold_mid=MID, min_chunks=MIN_CHUNKS,
    )
    assert confidence == "low"
