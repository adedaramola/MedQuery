"""
Unit tests for backend/pipeline/nodes.py

All OpenAI and pgvector calls are mocked — no network I/O.
"""
import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import make_state


# ---------------------------------------------------------------------------
# router_node
# ---------------------------------------------------------------------------

class TestRouterNode:
    def test_routes_to_medical_knowledge(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="medical_knowledge"))
        state = make_state(query="What causes diabetes?")
        result = nodes.router_node(state)
        assert result["source"] == "medical_knowledge"
        assert result["routed_to"] == "medical_knowledge"

    def test_routes_to_device(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="device_manual"))
        state = make_state(query="How do I use a ventilator?")
        result = nodes.router_node(state)
        assert result["source"] == "device_manual"

    def test_routes_to_web_search(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="web_search"))
        state = make_state(query="Latest COVID-19 news")
        result = nodes.router_node(state)
        assert result["source"] == "web_search"

    def test_routes_to_uploaded_document(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="uploaded_document"))
        state = make_state(query="What does the uploaded guideline say?")
        result = nodes.router_node(state)
        assert result["routed_to"] == "uploaded_document"

    def test_invalid_llm_response_falls_back_to_web_search(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="InvalidOption"))
        state = make_state(query="Random query")
        result = nodes.router_node(state)
        assert result["source"] == "web_search"

    def test_routing_reason_set(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="medical_knowledge"))
        state = make_state()
        result = nodes.router_node(state)
        assert "routing_reason" in result
        assert len(result["routing_reason"]) > 0


# ---------------------------------------------------------------------------
# route_decision
# ---------------------------------------------------------------------------

class TestRouteDecision:
    def test_returns_routed_to(self):
        from backend.pipeline.nodes import route_decision
        state = make_state(routed_to="medical_knowledge")
        assert route_decision(state) == "medical_knowledge"


# ---------------------------------------------------------------------------
# retrieve_clinical
# ---------------------------------------------------------------------------

class TestRetrieveClinical:
    def test_populates_context(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "query_qna", MagicMock(return_value=["Doc 1: Diabetes info.", "Doc 2: More."]))
        state = make_state(query="What is diabetes?")
        result = nodes.retrieve_clinical(state)
        assert result["context"] != ""
        assert result["source"] == "Medical Q&A Collection"

    def test_handles_empty_results(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "query_qna", MagicMock(return_value=[]))
        state = make_state(query="obscure query")
        result = nodes.retrieve_clinical(state)
        assert result["context"] == ""

    def test_handles_exception_gracefully(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "query_qna", MagicMock(side_effect=RuntimeError("DB error")))
        state = make_state()
        result = nodes.retrieve_clinical(state)
        assert result["context"] == ""


# ---------------------------------------------------------------------------
# retrieve_device
# ---------------------------------------------------------------------------

class TestRetrieveDevice:
    def test_populates_context(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "query_device", MagicMock(return_value=["Pacemaker doc 1.", "Pacemaker doc 2."]))
        state = make_state(query="How does a pacemaker work?")
        result = nodes.retrieve_device(state)
        assert result["context"] != ""
        assert result["source"] == "Medical Device Manual"

    def test_handles_exception_gracefully(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "query_device", MagicMock(side_effect=RuntimeError("DB error")))
        state = make_state()
        result = nodes.retrieve_device(state)
        assert result["context"] == ""


# ---------------------------------------------------------------------------
# retrieve_uploaded
# ---------------------------------------------------------------------------

class TestRetrieveUploaded:
    def test_populates_context(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "query_documents", MagicMock(return_value=["Chunk 1.", "Chunk 2."]))
        state = make_state(query="What does the uploaded guideline say?")
        result = nodes.retrieve_uploaded(state)
        assert "Chunk 1." in result["context"]
        assert result["source"] == "Uploaded Document"

    def test_handles_empty_results(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "query_documents", MagicMock(return_value=[]))
        state = make_state()
        result = nodes.retrieve_uploaded(state)
        assert result["context"] == ""
        assert result["source"] == "Uploaded Document"

    def test_handles_exception_gracefully(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "query_documents", MagicMock(side_effect=RuntimeError("DB error")))
        state = make_state()
        result = nodes.retrieve_uploaded(state)
        assert result["context"] == ""


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------

class TestWebSearch:
    def test_populates_context_on_success_via_tavily(self, monkeypatch):
        """With TAVILY_API_KEY set, uses Tavily."""
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "TAVILY_API_KEY", "tvly-fake-key")
        monkeypatch.setattr(
            nodes,
            "_web_search_tavily",
            MagicMock(return_value=["Tavily result 1.", "Tavily result 2."]),
        )
        state = make_state(query="Latest COVID news")
        result = nodes.web_search(state)
        assert "Tavily result 1." in result["context"]
        assert result["source"] == "Web Search (Tavily)"

    def test_empty_results(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "TAVILY_API_KEY", "tvly-fake-key")
        monkeypatch.setattr(nodes, "_web_search_tavily", MagicMock(return_value=[]))
        state = make_state(query="very obscure query")
        result = nodes.web_search(state)
        assert result["context"] == "No results found"

    def test_handles_exception_gracefully(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "TAVILY_API_KEY", "tvly-fake-key")
        monkeypatch.setattr(
            nodes,
            "_web_search_tavily",
            MagicMock(side_effect=RuntimeError("Network error")),
        )
        state = make_state()
        result = nodes.web_search(state)
        assert "Search error" in result["context"]
        assert result["source"] == "Web Search (failed)"

    def test_raises_error_when_no_tavily_key(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "TAVILY_API_KEY", "")
        state = make_state()
        result = nodes.web_search(state)
        assert "Search error" in result["context"]
        assert result["source"] == "Web Search (failed)"


# ---------------------------------------------------------------------------
# check_relevance
# ---------------------------------------------------------------------------

class TestCheckRelevance:
    def test_marks_relevant_yes(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="Yes"))
        state = make_state(iteration_count=0)
        result = nodes.check_relevance(state)
        assert result["is_relevant"] == "Yes"
        assert result["iteration_count"] == 1

    def test_marks_relevant_no(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="No"))
        state = make_state(iteration_count=0)
        result = nodes.check_relevance(state)
        assert result["is_relevant"] == "No"

    def test_max_iterations_forces_relevant(self, monkeypatch):
        from backend.pipeline import nodes
        from backend.config import MAX_ITERATIONS
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="No"))
        # iteration_count starts at MAX_ITERATIONS - 1, checker increments it to MAX
        state = make_state(iteration_count=MAX_ITERATIONS - 1)
        result = nodes.check_relevance(state)
        assert result["is_relevant"] == "Yes"
        assert result["iteration_count"] == MAX_ITERATIONS

    def test_increments_iteration_count(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="Yes"))
        state = make_state(iteration_count=1)
        result = nodes.check_relevance(state)
        assert result["iteration_count"] == 2

    def test_handles_llm_exception(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(side_effect=RuntimeError("LLM down")))
        state = make_state(iteration_count=0)
        result = nodes.check_relevance(state)
        # On error defaults to relevant so we don't loop forever
        assert result["is_relevant"] == "Yes"


# ---------------------------------------------------------------------------
# relevance_decision
# ---------------------------------------------------------------------------

class TestRelevanceDecision:
    def test_returns_is_relevant_field(self):
        from backend.pipeline.nodes import relevance_decision
        state = make_state(is_relevant="Yes")
        assert relevance_decision(state) == "Yes"

    def test_returns_no(self):
        from backend.pipeline.nodes import relevance_decision
        state = make_state(is_relevant="No")
        assert relevance_decision(state) == "No"


# ---------------------------------------------------------------------------
# augment
# ---------------------------------------------------------------------------

class TestAugment:
    def test_builds_prompt_with_context(self):
        from backend.pipeline.nodes import augment
        state = make_state(context="Diabetes is a metabolic disease.", history=[])
        result = augment(state)
        assert "Diabetes is a metabolic disease." in result["prompt"]
        assert "What are symptoms of diabetes?" in result["prompt"]

    def test_includes_history_block(self):
        from backend.pipeline.nodes import augment
        history = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there"}]
        state = make_state(history=history)
        result = augment(state)
        assert "Previous conversation:" in result["prompt"]
        assert "Hello" in result["prompt"]

    def test_empty_context_message(self):
        from backend.pipeline.nodes import augment
        state = make_state(context="")
        result = augment(state)
        assert "No relevant context was retrieved." in result["prompt"]

    def test_no_history_no_history_block(self):
        from backend.pipeline.nodes import augment
        state = make_state(history=[])
        result = augment(state)
        assert "Previous conversation:" not in result["prompt"]


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

class TestGenerate:
    def test_generates_response(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(return_value="Generated answer."))
        state = make_state(prompt="Answer the question about diabetes.")
        result = nodes.generate(state)
        assert result["response"] == "Generated answer."
        # source_quality is now a dict descriptor, not a float
        assert isinstance(result["source_quality"], dict)
        assert "tier" in result["source_quality"]

    def test_handles_llm_error(self, monkeypatch):
        from backend.pipeline import nodes
        monkeypatch.setattr(nodes, "get_llm_response", MagicMock(side_effect=RuntimeError("API error")))
        state = make_state(prompt="Some prompt")
        result = nodes.generate(state)
        assert "Error generating response" in result["response"]
        assert result["source_quality"] is None


# ---------------------------------------------------------------------------
# _build_history_block (internal helper)
# ---------------------------------------------------------------------------

class TestBuildHistoryBlock:
    def test_empty_history(self):
        from backend.pipeline.nodes import _build_history_block
        assert _build_history_block([]) == ""

    def test_formats_user_and_assistant(self):
        from backend.pipeline.nodes import _build_history_block
        history = [
            {"role": "user", "content": "What is aspirin?"},
            {"role": "assistant", "content": "Aspirin is an analgesic."},
        ]
        block = _build_history_block(history)
        assert "User: What is aspirin?" in block
        assert "Assistant: Aspirin is an analgesic." in block
        assert block.startswith("Previous conversation:")
