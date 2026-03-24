"""
Shared pytest fixtures for the Medical Agentic RAG test suite.

All external I/O (PostgreSQL, OpenAI) is mocked so tests run
offline with no real database or API calls.
"""
import os

# ── Provide a dummy API key before any backend modules are imported ──────────
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-tests")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test_db")

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Minimal GraphState factory
# ---------------------------------------------------------------------------

_DEFAULT_SOURCE_QUALITY = {
    "tier": "verified_corpus",
    "label": "Verified corpus (structured medical data)",
    "is_relevant": True,
    "iterations": 1,
    "disclaimer": (
        "Source quality reflects the retrieval origin, not answer correctness. "
        "Always verify medical information with a qualified healthcare professional."
    ),
}


def make_state(**overrides) -> dict:
    """Return a fully-populated GraphState dict with sensible defaults."""
    base = {
        "query": "What are symptoms of diabetes?",
        "context": "Diabetes symptoms include increased thirst and frequent urination.",
        "prompt": "",
        "response": "",
        "source": "Medical Q&A Collection",
        "routed_to": "medical_knowledge",
        "routing_reason": "Routed to medical_knowledge",
        "is_relevant": "Yes",
        "relevance_reason": "Context is relevant",
        "iteration_count": 1,
        "history": [],
        "source_quality": _DEFAULT_SOURCE_QUALITY,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Mock PostgreSQL connection helper
# ---------------------------------------------------------------------------

def make_mock_conn(fetchall=None, fetchone=None):
    """Build a mock psycopg2 connection + cursor."""
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.return_value = fetchall or []
    mock_cursor.fetchone.return_value = fetchone or (0,)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    """
    TestClient for the FastAPI app with all DB calls mocked.
    - init_schema / init_history_schema → no-ops
    - count_qna / count_device → return 100 / 50
    """
    import backend.vector_store as vs
    import backend.history as hist_mod

    monkeypatch.setattr(vs, "init_schema", MagicMock())
    monkeypatch.setattr(vs, "count_qna", MagicMock(return_value=100))
    monkeypatch.setattr(vs, "count_device", MagicMock(return_value=50))
    monkeypatch.setattr(hist_mod, "init_history_schema", MagicMock())

    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def client_with_api_key(monkeypatch):
    """TestClient with API key enforcement enabled."""
    import backend.vector_store as vs
    import backend.history as hist_mod
    import backend.config as cfg
    import backend.auth as auth_mod

    monkeypatch.setattr(vs, "init_schema", MagicMock())
    monkeypatch.setattr(vs, "count_qna", MagicMock(return_value=100))
    monkeypatch.setattr(vs, "count_device", MagicMock(return_value=50))
    monkeypatch.setattr(hist_mod, "init_history_schema", MagicMock())
    monkeypatch.setattr(cfg, "API_KEY", "test-secret-key")
    monkeypatch.setattr(auth_mod, "API_KEY", "test-secret-key", raising=False)

    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
