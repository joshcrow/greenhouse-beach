#!/usr/bin/env bash
set -euo pipefail

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [entrypoint] Starting Greenhouse Storyteller Services..."

# Start ingestion in background
python -u scripts/ingestion.py &
INGESTION_PID=$!

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [entrypoint] Started ingestion.py (PID=${INGESTION_PID})"

# Start curator in background
python -u scripts/curator.py &
CURATOR_PID=$!

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [entrypoint] Started curator.py (PID=${CURATOR_PID})"

# Start scheduler in background
python -u scripts/scheduler.py &
SCHEDULER_PID=$!

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [entrypoint] Started scheduler.py (PID=${SCHEDULER_PID})"

# Wait for the first process to exit; let Docker handle restart policy
wait -n

EXIT_CODE=$?
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [entrypoint] Child process exited with code ${EXIT_CODE}, stopping container."
exit "${EXIT_CODE}"
