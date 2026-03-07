import threading
import psycopg2
import psycopg2.pool
from pgvector.psycopg2 import register_vector

from backend.config import DATABASE_URL

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_lock = threading.Lock()


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    with _lock:
        if _pool is None:
            _pool = psycopg2.pool.ThreadedConnectionPool(1, 20, DATABASE_URL)
    return _pool


def get_conn() -> psycopg2.extensions.connection:
    """Return a plain connection. Callers that use vector columns must call
    register_vector(conn) themselves after the pgvector extension exists."""
    return get_pool().getconn()


def get_vector_conn() -> psycopg2.extensions.connection:
    """Return a connection with the pgvector adapter registered.
    Only call this after init_schema() has created the vector extension."""
    conn = get_pool().getconn()
    register_vector(conn)
    return conn


def put_conn(conn: psycopg2.extensions.connection) -> None:
    get_pool().putconn(conn)
