#!/bin/sh
set -e

echo ">>> Running database migrations..."
alembic upgrade head

echo ">>> Starting backend..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
