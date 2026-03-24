from typing import Optional, List
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    conversation_id: Optional[str] = None


class SourceInfo(BaseModel):
    routing: str
    reason: str


class RelevanceInfo(BaseModel):
    is_relevant: bool
    reason: Optional[str] = None


class SourceQualityInfo(BaseModel):
    """
    Describes the trustworthiness of the retrieval *source*.
    This is NOT a confidence score for answer correctness.
    """
    tier: str
    label: str
    is_relevant: bool
    iterations: int
    disclaimer: str


class QueryResponse(BaseModel):
    query: str
    answer: str
    source: str
    source_info: SourceInfo
    relevance: RelevanceInfo
    context: str
    iteration_count: int
    # Renamed from 'confidence': describes source origin, not answer correctness.
    source_quality: Optional[SourceQualityInfo] = None
    timestamp: str
    conversation_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    models: dict
    databases: dict


class GraphState(TypedDict):
    query: str
    context: str
    prompt: str
    response: str
    source: str
    routed_to: str
    routing_reason: str
    is_relevant: str
    relevance_reason: Optional[str]
    iteration_count: int
    history: List[dict]
    source_quality: Optional[dict]  # replaces 'confidence'; see pipeline/state.py
