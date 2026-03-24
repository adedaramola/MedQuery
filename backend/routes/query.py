import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.auth import require_api_key
from backend.limiter import limiter
from backend.models import QueryRequest, QueryResponse, SourceInfo, RelevanceInfo, SourceQualityInfo
from backend.history import get_history, save_turn
from backend.pipeline import query_rag, stream_rag_response
from backend.safety import RiskLevel, check_safety, append_safety_disclaimer

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
async def api_query(request: Request, body: QueryRequest):
    logger.info(f"Query received: {body.query[:50]}...")

    # --- Safety gate ---
    safety = check_safety(body.query)
    if safety.risk_level == RiskLevel.BLOCKED:
        logger.warning("Query blocked by safety guardrails")
        return QueryResponse(
            query=body.query,
            answer=safety.safe_response,
            source="Safety Guardrail",
            source_info=SourceInfo(routing="blocked", reason=safety.reason),
            relevance=RelevanceInfo(is_relevant=False, reason="Blocked before retrieval"),
            context="",
            iteration_count=0,
            source_quality=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            conversation_id=body.conversation_id,
        )

    try:
        history = get_history(body.conversation_id)
        result = query_rag(body.query, history)
        answer = append_safety_disclaimer(result["response"], safety)
        save_turn(body.conversation_id, body.query, answer)

        return QueryResponse(
            query=result["query"],
            answer=answer,
            source=result["source"],
            source_info=SourceInfo(
                routing=result["routed_to"],
                reason=result["routing_reason"],
            ),
            relevance=RelevanceInfo(
                is_relevant=result["is_relevant"].lower() == "yes",
                reason=result["relevance_reason"],
            ),
            context=result["context"][:200],
            iteration_count=result["iteration_count"],
            source_quality=SourceQualityInfo(**result["source_quality"]) if result.get("source_quality") else None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            conversation_id=body.conversation_id,
        )
    except Exception as e:
        logger.error(f"Query error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")


@router.post("/query/stream", dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
async def api_query_stream(request: Request, body: QueryRequest):
    """Streaming RAG endpoint (SSE): meta → token* → done."""
    logger.info(f"Stream query received: {body.query[:50]}...")

    # --- Safety gate ---
    safety = check_safety(body.query)
    if safety.risk_level == RiskLevel.BLOCKED:
        logger.warning("Stream query blocked by safety guardrails")

        async def blocked_generator():
            yield f"data: {json.dumps({'type': 'meta', 'source': 'Safety Guardrail', 'source_info': {'routing': 'blocked', 'reason': safety.reason}, 'relevance': {'is_relevant': False, 'reason': 'Blocked before retrieval'}, 'context': ''})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'answer': safety.safe_response, 'source_quality': None, 'iteration_count': 0, 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"

        return StreamingResponse(
            blocked_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    history = get_history(body.conversation_id)

    async def event_generator():
        full_answer = ""
        async for event in stream_rag_response(body.query, history):
            # Append safety disclaimer to the done event if flagged
            if safety.risk_level == RiskLevel.FLAGGED and event.startswith("data: "):
                try:
                    payload = json.loads(event[6:])
                    if payload.get("type") == "done":
                        payload["answer"] = append_safety_disclaimer(payload["answer"], safety)
                        event = f"data: {json.dumps(payload)}\n\n"
                except Exception:
                    pass
            yield event
            if event.startswith("data: "):
                try:
                    payload = json.loads(event[6:])
                    if payload.get("type") == "done":
                        full_answer = payload.get("answer", "")
                except Exception:
                    pass
        if full_answer:
            save_turn(body.conversation_id, body.query, full_answer)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
