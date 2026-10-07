#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="/home/chirag/Desktop/Meridian"
STACK_UNIT="meridian-hadoop-stack.service"
STREAM_UNIT="meridian-stream-consumer.service"
LOCK_FILE="/tmp/meridian-local-pipeline.lock"

cd "$PROJECT_ROOT"
source /home/chirag/bigdata/env.sh

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another Meridian local pipeline run is already active." >&2
  exit 1
fi

if systemctl --user is-active --quiet "$STREAM_UNIT"; then
  echo "$STREAM_UNIT is active. Stop it before running the finite batch pipeline:" >&2
  echo "  systemctl --user stop $STREAM_UNIT" >&2
  exit 1
fi

started_stack=0
cleanup() {
  local exit_code=$?
  if (( started_stack == 1 )); then
    echo "Stopping local Hadoop/Hive stack..."
    systemctl --user stop "$STACK_UNIT" || true
  fi
  trap - EXIT
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

if ! systemctl --user is-active --quiet "$STACK_UNIT"; then
  echo "Starting local HDFS, YARN, and Hive stack..."
  systemctl --user start "$STACK_UNIT"
  started_stack=1
else
  echo "Using already-running local Hadoop/Hive stack."
fi

echo "Processing accumulated live landing files with Spark..."
MERIDIAN_BATCH_MODE=1 timeout 2h "$SPARK_HOME/bin/spark-shell" \
  -i "$PROJECT_ROOT/spark/stream_alchemy_live.scala"

echo "Exporting dashboard data..."
timeout 2h "$SPARK_HOME/bin/spark-shell" \
  -i "$PROJECT_ROOT/spark/export_dashboard_data.scala"

echo "Generating best-effort risk advisories..."
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/ingestion/generate_risk_advisories.py"

echo "Publishing dashboard data to Supabase..."
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/ingestion/push_to_supabase.py"

echo "Local pipeline complete. Heavy services will now stop if this script started them."