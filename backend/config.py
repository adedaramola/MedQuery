import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not set in .env file")

LLM_MODEL: str = "gpt-4o-mini"
EMBED_MODEL: str = "text-embedding-3-small"
DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://localhost/medical_rag")
N_RESULTS: int = 5
MAX_ITERATIONS: int = 3
MAX_HISTORY_TURNS: int = int(os.getenv("MAX_HISTORY_TURNS", "10"))
# Approximate token budget per history turn (used for token-aware truncation).
# gpt-4o-mini averages ~4 chars/token; 300 tokens ≈ 1200 chars per turn.
MAX_TOKENS_PER_TURN: int = 300
API_VERSION: str = "1.0.0"

# Security
# Comma-separated list of allowed origins, e.g. "http://localhost:3000,https://yourapp.com"
ALLOWED_ORIGINS: list = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
# Optional API key. If set, all /api/query requests must include header: X-API-Key: <value>
# Leave unset (or empty) during local development to skip auth.
API_KEY: str = os.getenv("API_KEY", "")

# Web search provider — Tavily (required for web_search node)
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON object — easy to parse in log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Attach request_id if the middleware injected it onto the record.
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


_handler = logging.StreamHandler()
_handler.setFormatter(_JsonFormatter())

logging.basicConfig(level=logging.INFO, handlers=[_handler])
