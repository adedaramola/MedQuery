"""
Integration tests for FastAPI routes.

All external I/O (OpenAI, pgvector, Tavily) is mocked.
The TestClient exercises the full request/response cycle.
"""
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from tests.conftest import make_state


# ---------------------------------------------------------------------------
# Helpers — build a complete pipeline result
# ---------------------------------------------------------------------------

def _pipeline_result(**overrides) -> dict:
    result = make_state(
        query="What are symptoms of diabetes?",
        response="Diabetes symptoms include increased thirst.",
        source="Medical Q&A Collection",
        routed_to="medical_knowledge",
        routing_reason="Routed to medical_knowledge",
        is_relevant="Yes",
        relevance_reason="Context is relevant",
        iteration_count=1,
        context="Retrieved context about diabetes.",
        # source_quality is set by make_state default
    )
    result.update(overrides)
    return result


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_returns_200(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_response_shape(self, client):
        response = client.get("/api/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "models" in data
        assert "databases" in data

    def test_models_keys(self, client):
        data = client.get("/api/health").json()
        assert "llm" in data["models"]
        assert "embeddings" in data["models"]

    def test_databases_keys(self, client):
        data = client.get("/api/health").json()
        db = data["databases"]
        assert "database_url" in db
        assert "qa_collection_count" in db
        assert "device_collection_count" in db

    def test_x_request_id_header_present(self, client):
        response = client.get("/api/health")
        assert "x-request-id" in response.headers


# ---------------------------------------------------------------------------
# GET /  (root)
# ---------------------------------------------------------------------------

class TestRootEndpoint:
    def test_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_service_name(self, client):
        data = client.get("/").json()
        assert "service" in data or "status" in data  # root redirects to health


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------

class TestQueryEndpoint:
    def test_returns_200(self, client):
        with patch("backend.routes.query.query_rag", return_value=_pipeline_result()), \
             patch("backend.routes.query.save_turn"):
            response = client.post("/api/query", json={"query": "What is diabetes?"})
        assert response.status_code == 200

    def test_response_fields(self, client):
        with patch("backend.routes.query.query_rag", return_value=_pipeline_result()), \
             patch("backend.routes.query.save_turn"):
            data = client.post("/api/query", json={"query": "What is diabetes?"}).json()
        assert "query" in data
        assert "answer" in data
        assert "source" in data
        assert "source_quality" in data   # renamed from 'confidence'
        assert "iteration_count" in data
        assert "timestamp" in data

    def test_answer_content(self, client):
        with patch("backend.routes.query.query_rag", return_value=_pipeline_result()), \
             patch("backend.routes.query.save_turn"):
            data = client.post("/api/query", json={"query": "What is diabetes?"}).json()
        assert "Diabetes" in data["answer"] or len(data["answer"]) > 0

    def test_empty_query_rejected(self, client):
        response = client.post("/api/query", json={"query": ""})
        assert response.status_code == 422

    def test_query_too_long_rejected(self, client):
        response = client.post("/api/query", json={"query": "x" * 501})
        assert response.status_code == 422

    def test_missing_query_field_rejected(self, client):
        response = client.post("/api/query", json={})
        assert response.status_code == 422

    def test_conversation_id_echoed(self, client):
        with patch("backend.routes.query.query_rag", return_value=_pipeline_result()), \
             patch("backend.routes.query.save_turn"), \
             patch("backend.routes.query.get_history", return_value=[]):
            data = client.post(
                "/api/query",
                json={"query": "What is diabetes?", "conversation_id": "test-conv-123"},
            ).json()
        assert data.get("conversation_id") == "test-conv-123"

    def test_source_info_shape(self, client):
        with patch("backend.routes.query.query_rag", return_value=_pipeline_result()), \
             patch("backend.routes.query.save_turn"):
            data = client.post("/api/query", json={"query": "What is diabetes?"}).json()
        assert "routing" in data["source_info"]
        assert "reason" in data["source_info"]

    def test_relevance_shape(self, client):
        with patch("backend.routes.query.query_rag", return_value=_pipeline_result()), \
             patch("backend.routes.query.save_turn"):
            data = client.post("/api/query", json={"query": "What is diabetes?"}).json()
        assert "is_relevant" in data["relevance"]

    def test_500_on_pipeline_error(self, client):
        with patch("backend.routes.query.query_rag", side_effect=RuntimeError("Pipeline failed")):
            response = client.post("/api/query", json={"query": "What is diabetes?"})
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/query/stream  (SSE)
# ---------------------------------------------------------------------------

class TestQueryStreamEndpoint:
    def _make_sse_generator(self, query="What is diabetes?"):
        """Build an async generator that yields realistic SSE events."""
        answer = "Diabetes symptoms include thirst."
        source_quality = {
            "tier": "verified_corpus",
            "label": "Verified corpus (structured medical data)",
            "is_relevant": True,
            "iterations": 1,
            "disclaimer": "Source quality reflects retrieval origin, not answer correctness.",
        }
        events = [
            f'data: {json.dumps({"type": "meta", "source": "Medical Q&A Collection", "source_info": {"routing": "medical_knowledge", "reason": "Routed"}, "relevance": {"is_relevant": True}, "context": "ctx"})}\n\n',
            f'data: {json.dumps({"type": "token", "token": "Diabetes "})}\n\n',
            f'data: {json.dumps({"type": "token", "token": "symptoms."})}\n\n',
            f'data: {json.dumps({"type": "done", "answer": answer, "source_quality": source_quality, "iteration_count": 1, "timestamp": "2024-01-01T00:00:00"})}\n\n',
        ]

        async def _gen():
            for e in events:
                yield e

        return _gen()

    def test_returns_200_with_event_stream(self, client):
        with patch("backend.routes.query.stream_rag_response", return_value=self._make_sse_generator()), \
             patch("backend.routes.query.save_turn"), \
             patch("backend.routes.query.get_history", return_value=[]):
            response = client.post("/api/query/stream", json={"query": "What is diabetes?"})
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_stream_contains_data_lines(self, client):
        with patch("backend.routes.query.stream_rag_response", return_value=self._make_sse_generator()), \
             patch("backend.routes.query.save_turn"), \
             patch("backend.routes.query.get_history", return_value=[]):
            response = client.post("/api/query/stream", json={"query": "What is diabetes?"})
        assert b"data:" in response.content

    def test_stream_contains_done_event(self, client):
        with patch("backend.routes.query.stream_rag_response", return_value=self._make_sse_generator()), \
             patch("backend.routes.query.save_turn"), \
             patch("backend.routes.query.get_history", return_value=[]):
            response = client.post("/api/query/stream", json={"query": "What is diabetes?"})
        assert b'"type": "done"' in response.content or b'"type":"done"' in response.content

    def test_empty_query_rejected(self, client):
        response = client.post("/api/query/stream", json={"query": ""})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/ingest
# ---------------------------------------------------------------------------

class TestIngestEndpoint:
    def test_returns_200(self, client):
        with patch("backend.routes.health.ingest_data", return_value={"qa": 100, "device": 50}):
            response = client.post("/api/ingest")
        assert response.status_code == 200

    def test_response_shape(self, client):
        with patch("backend.routes.health.ingest_data", return_value={"qa": 100, "device": 50}):
            data = client.post("/api/ingest").json()
        assert data["status"] == "success"
        assert data["qa_records"] == 100
        assert data["device_records"] == 50

    def test_custom_sample_size(self, client):
        with patch("backend.routes.health.ingest_data", return_value={"qa": 200, "device": 100}) as mock_ingest:
            client.post("/api/ingest?sample_size=200")
        mock_ingest.assert_called_once_with(sample_size=200)

    def test_sample_size_below_minimum_rejected(self, client):
        response = client.post("/api/ingest?sample_size=0")
        assert response.status_code == 422

    def test_sample_size_above_maximum_rejected(self, client):
        response = client.post("/api/ingest?sample_size=9999")
        assert response.status_code == 422

    def test_500_on_ingest_error(self, client):
        with patch("backend.routes.health.ingest_data", side_effect=RuntimeError("Ingest failed")):
            response = client.post("/api/ingest")
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------

class TestApiKeyAuth:
    def test_query_passes_without_api_key_when_not_configured(self, client):
        """When API_KEY env var is empty, all requests should pass."""
        with patch("backend.routes.query.query_rag", return_value=_pipeline_result()), \
             patch("backend.routes.query.save_turn"):
            response = client.post("/api/query", json={"query": "test"})
        assert response.status_code == 200

    def test_query_blocked_with_wrong_api_key(self, client_with_api_key):
        response = client_with_api_key.post(
            "/api/query",
            json={"query": "test"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_query_passes_with_correct_api_key(self, client_with_api_key):
        with patch("backend.routes.query.query_rag", return_value=_pipeline_result()), \
             patch("backend.routes.query.save_turn"):
            response = client_with_api_key.post(
                "/api/query",
                json={"query": "test"},
                headers={"X-API-Key": "test-secret-key"},
            )
        assert response.status_code == 200

    def test_query_blocked_without_api_key_when_configured(self, client_with_api_key):
        response = client_with_api_key.post("/api/query", json={"query": "test"})
        assert response.status_code == 403
