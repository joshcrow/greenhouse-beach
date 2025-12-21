#!/usr/bin/env bash
set -euo pipefail

# Handler for SIGTERM/SIGINT to gracefully stop children
cleanup() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [entrypoint] Received termination signal, stopping services..."
    kill -TERM "$INGESTION_PID" 2>/dev/null || true
    kill -TERM "$CURATOR_PID" 2>/dev/null || true
    kill -TERM "$SCHEDULER_PID" 2>/dev/null || true
    kill -TERM "$STATUS_PID" 2>/dev/null || true
    kill -TERM "$WEBSERVER_PID" 2>/dev/null || true
    wait
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [entrypoint] Services stopped."
    exit 0
}

trap cleanup SIGTERM SIGINT

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

# Start status daemon (live snapshot + 24h stats) in background
python -u scripts/status_daemon.py &
STATUS_PID=$!
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [entrypoint] Started status_daemon.py (PID=${STATUS_PID})"

# Start web server for timelapse downloads
python -u scripts/web_server.py &
WEBSERVER_PID=$!
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [entrypoint] Started web_server.py (PID=${WEBSERVER_PID})"

# Wait for the first process to exit; let Docker handle restart policy
# Note: wait -n is not available in all shells, but standard in bash 4.3+ (Debian/Alpine usually have it)
# However, with trap, we need a loop or wait on specific PIDs to keep trap active.
# Simple wait will return when a signal is caught.

wait "$INGESTION_PID" "$CURATOR_PID" "$SCHEDULER_PID" "$STATUS_PID" "$WEBSERVER_PID"

EXIT_CODE=$?
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [entrypoint] Child process exited with code ${EXIT_CODE}, stopping container."
exit "${EXIT_CODE}"
