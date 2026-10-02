#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="/home/chirag/Desktop/Meridian"
cd "$PROJECT_ROOT"

# Prevent two feed processes from competing for the same Alchemy stream and
# state file. The foreground launcher owns the process until Ctrl+C/TERM.
if systemctl --user is-active --quiet meridian-live-feed.service; then
  echo "meridian-live-feed.service is already running." >&2
  echo "Stop it first with: systemctl --user stop meridian-live-feed.service" >&2
  exit 1
fi

if [[ ! -x "$PROJECT_ROOT/.venv/bin/python3" ]]; then
  echo "Missing Python environment at $PROJECT_ROOT/.venv" >&2
  exit 1
fi

echo "Starting live activity feed in the foreground. Press Ctrl+C to stop it."
echo "Hadoop, Hive, and Spark are not started by this launcher."
exec env PYTHONUNBUFFERED=1 "$PROJECT_ROOT/.venv/bin/python3" \
  "$PROJECT_ROOT/ingestion/alchemy_live_feed.py"