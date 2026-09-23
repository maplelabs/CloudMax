#!/bin/bash

# Backend entrypoint script for SRE Alert Dashboard
# This script handles different startup modes for the backend service

set -e

# Default values
MODE=${MODE:-"server"}
HOST=${HOST:-"0.0.0.0"}
PORT=${PORT:-"8000"}

echo "Mode: $MODE"

case "$MODE" in
    "server")
        echo "Starting FastAPI server..."
        echo "Host: $HOST"
        echo "Port: $PORT"

        # Start the FastAPI server
        exec uvicorn src.server.web:app --host "$HOST" --port "$PORT"
        ;;
    "triager")
        echo "Starting RQ triager ..."
        exec python -m src.server.async_workers.triager
        ;;
    "evaluator")
        echo "Starting RQ evaluator ..."
        exec python -m src.server.async_workers.evaluator
        ;;
    "grouper")
        echo "Starting RQ grouper ..."
        exec python -m src.server.async_workers.grouper
        ;;
    "job-scheduler")
        echo "Starting RQ job scheduler ..."

        # Run one-time startup cleanup to remove old duplicate triages
        # This runs only once when job-scheduler starts (not on every backend restart)
        echo "Running one-time startup cleanup..."
        python -m src.server.startup_cleanup

        # Schedule periodic jobs (batch grouping, etc.)
        echo "Scheduling periodic jobs..."
        python -m src.server.schedule_jobs

        # Start the RQ scheduler
        exec rqscheduler --host "$REDIS_QUEUE_HOST" --port "$REDIS_QUEUE_PORT" --db "$REDIS_QUEUE_DB" --password "$REDIS_QUEUE_AUTH" --interval 30
        ;;
    "migrate")
        echo "Running database migrations..."
        exec alembic -c src/alembic.ini upgrade head
        ;;
    *)
        echo "Unknown mode: $MODE"
        echo "Available modes: server, triager, evaluator, grouper, job-scheduler, migrate"
        exit 1
        ;;
esac
