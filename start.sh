#!/usr/bin/env sh
# Single-process-group startup for free hosting (one container runs everything):
#   1. apply DB migrations
#   2. start the Celery worker in the background
#   3. run the API in the foreground (must bind $PORT for Render)
set -e

alembic upgrade head

celery -A app.workers.celery_app worker --loglevel=info --concurrency=1 &

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
