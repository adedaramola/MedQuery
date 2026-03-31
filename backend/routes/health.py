import logging

from fastapi import APIRouter, HTTPException, Query

from backend.config import LLM_MODEL, EMBED_MODEL, DATABASE_URL, API_VERSION
from backend.models import HealthResponse
from backend.vector_store import count_qna, count_device, ingest_data

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        version=API_VERSION,
        models={"llm": LLM_MODEL, "embeddings": EMBED_MODEL},
        databases={
            "database_url": DATABASE_URL.split("@")[-1],  # strip credentials
            "qa_collection_count": count_qna(),
            "device_collection_count": count_device(),
        },
    )


@router.post("/ingest")
async def ingest(
    sample_size: int = Query(default=500, ge=1, le=5000),
):
    try:
        counts = ingest_data(sample_size=sample_size)
        logger.info(f"Data ingestion completed: {counts}")
        return {"status": "success", "qa_records": counts["qa"], "device_records": counts["device"]}
    except Exception as e:
        logger.error(f"Ingestion error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def root():
    return {
        "service": "MedQuery",
        "version": API_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }
