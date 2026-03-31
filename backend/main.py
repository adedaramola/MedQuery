import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.config import API_VERSION, ALLOWED_ORIGINS
from backend.limiter import limiter
from backend.vector_store import init_schema
from backend.history import init_history_schema
from backend.routes.query import router as query_router
from backend.routes.health import router as health_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MedQuery Backend")
    try:
        init_schema()
        init_history_schema()
        logger.info("PostgreSQL schema ready")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="MedQuery",
    description="Medical question-answering system with intelligent routing and relevance checking",
    version=API_VERSION,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(query_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.add_api_route("/", health_router.routes[-1].endpoint)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Assigns a unique ID to every request.
    - Stores it on request.state so route handlers can reference it.
    - Injects it into all log records emitted during this request via a logging.Filter.
    - Returns it to the caller in the X-Request-ID response header.
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    class _RequestIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.request_id = request_id
            return True

    root_logger = logging.getLogger()
    f = _RequestIdFilter()
    root_logger.addFilter(f)
    try:
        response = await call_next(request)
    finally:
        root_logger.removeFilter(f)

    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"Unhandled error: {str(exc)}", extra={"request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc), "request_id": request_id},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
