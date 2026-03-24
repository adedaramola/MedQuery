"""
Unit tests for backend/pipeline/state.py :: compute_source_quality

Validates that the source-quality descriptor correctly reflects
retrieval origin (tier, label, relevance, iterations) and includes
the required disclaimer. Does NOT test for numeric confidence values —
those were removed as misleading.
"""
import pytest
from tests.conftest import make_state
from backend.pipeline.state import compute_source_quality


class TestComputeSourceQuality:
    # ── Tier assignment by source ─────────────────────────────────────────

    def test_qna_source_is_verified_corpus(self):
        state = make_state(source="Medical Q&A Collection", is_relevant="Yes", iteration_count=1)
        result = compute_source_quality(state)
        assert result["tier"] == "verified_corpus"

    def test_device_source_is_verified_corpus(self):
        state = make_state(source="Medical Device Manual", is_relevant="Yes", iteration_count=1)
        result = compute_source_quality(state)
        assert result["tier"] == "verified_corpus"

    def test_web_search_tavily_is_external_web(self):
        state = make_state(source="Web Search (Tavily)", is_relevant="Yes", iteration_count=1)
        result = compute_source_quality(state)
        assert result["tier"] == "external_web"

    def test_web_search_duckduckgo_is_external_web(self):
        state = make_state(source="Web Search (DuckDuckGo)", is_relevant="Yes", iteration_count=1)
        result = compute_source_quality(state)
        assert result["tier"] == "external_web"

    def test_failed_web_search_is_failed(self):
        state = make_state(source="Web Search (failed)", is_relevant="Yes", iteration_count=1)
        result = compute_source_quality(state)
        assert result["tier"] == "failed"

    def test_unknown_source_is_unknown(self):
        state = make_state(source="SomeOtherSource", is_relevant="Yes", iteration_count=1)
        result = compute_source_quality(state)
        assert result["tier"] == "unknown"

    # ── Label is a non-empty human-readable string ────────────────────────

    def test_label_is_string(self):
        for source in ["Medical Q&A Collection", "Web Search (Tavily)", "Web Search (failed)", ""]:
            result = compute_source_quality(make_state(source=source))
            assert isinstance(result["label"], str)
            assert len(result["label"]) > 0

    # ── Relevance is reflected ────────────────────────────────────────────

    def test_relevant_true_when_yes(self):
        state = make_state(is_relevant="Yes")
        assert compute_source_quality(state)["is_relevant"] is True

    def test_relevant_false_when_no(self):
        state = make_state(is_relevant="No")
        assert compute_source_quality(state)["is_relevant"] is False

    def test_relevant_case_insensitive_yes(self):
        for val in ("YES", "yes", "Yes"):
            assert compute_source_quality(make_state(is_relevant=val))["is_relevant"] is True

    # ── Iterations are reflected ──────────────────────────────────────────

    def test_iterations_stored(self):
        for n in (1, 2, 3):
            result = compute_source_quality(make_state(iteration_count=n))
            assert result["iterations"] == n

    # ── Disclaimer is always present ──────────────────────────────────────

    def test_disclaimer_always_present(self):
        for source in ["Medical Q&A Collection", "Web Search (Tavily)", ""]:
            result = compute_source_quality(make_state(source=source))
            assert "disclaimer" in result
            assert len(result["disclaimer"]) > 20

    def test_disclaimer_mentions_professional(self):
        result = compute_source_quality(make_state())
        assert "healthcare professional" in result["disclaimer"].lower() or \
               "professional" in result["disclaimer"].lower()

    # ── Return type is always dict ────────────────────────────────────────

    def test_always_returns_dict(self):
        state = make_state(source="", is_relevant="Yes", iteration_count=1)
        result = compute_source_quality(state)
        assert isinstance(result, dict)
        for key in ("tier", "label", "is_relevant", "iterations", "disclaimer"):
            assert key in result
