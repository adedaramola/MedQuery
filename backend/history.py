import logging
from typing import Optional, List

from backend.config import MAX_HISTORY_TURNS, MAX_TOKENS_PER_TURN
from backend.db import get_conn, put_conn

logger = logging.getLogger(__name__)


def init_history_schema() -> None:
    """Create the conversation_turns table (idempotent)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id              SERIAL PRIMARY KEY,
                    conversation_id TEXT      NOT NULL,
                    role            TEXT      NOT NULL,
                    content         TEXT      NOT NULL,
                    created_at      TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conv_id
                ON conversation_turns(conversation_id)
            """)
            conn.commit()
    finally:
        put_conn(conn)


def _truncate_to_token_budget(turns: List[dict], max_tokens: int) -> List[dict]:
    """
    Drop the oldest turns until the total estimated token count is under budget.

    Uses a simple char-count heuristic (4 chars ≈ 1 token) to avoid importing
    tiktoken at runtime. Always retains at least the most recent turn pair.
    """
    # Approximate: 4 chars per token
    def _est_tokens(t: dict) -> int:
        return max(1, len(t.get("content", "")) // 4)

    total = sum(_est_tokens(t) for t in turns)
    while total > max_tokens and len(turns) > 2:
        dropped = turns.pop(0)
        total -= _est_tokens(dropped)
    return turns


def get_history(conversation_id: Optional[str]) -> List[dict]:
    """
    Return recent turns for a conversation, bounded by both MAX_HISTORY_TURNS
    (turn count) and MAX_TOKENS_PER_TURN * MAX_HISTORY_TURNS (token budget).

    Token-aware truncation prevents long prior turns from blowing out the
    LLM context window even when turn count is within the limit.
    """
    if not conversation_id:
        return []
    limit = MAX_HISTORY_TURNS * 2   # rows = 2× turns (user + assistant per turn)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content
                    FROM conversation_turns
                    WHERE conversation_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                ) sub
                ORDER BY id ASC
                """,
                (conversation_id, limit),
            )
            rows = cur.fetchall()
        turns = [{"role": row[0], "content": row[1]} for row in rows]
        token_budget = MAX_HISTORY_TURNS * MAX_TOKENS_PER_TURN
        return _truncate_to_token_budget(turns, token_budget)
    finally:
        put_conn(conn)


def save_turn(conversation_id: Optional[str], user_msg: str, assistant_msg: str) -> None:
    """Persist one user + assistant turn."""
    if not conversation_id:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conversation_turns (conversation_id, role, content) VALUES (%s, %s, %s)",
                (conversation_id, "user", user_msg),
            )
            cur.execute(
                "INSERT INTO conversation_turns (conversation_id, role, content) VALUES (%s, %s, %s)",
                (conversation_id, "assistant", assistant_msg),
            )
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Save turn error: {e}")
        raise
    finally:
        put_conn(conn)
