#!/usr/bin/env bash
set -Eeuo pipefail

source /home/chirag/bigdata/env.sh
cd /home/chirag/Desktop/Meridian

wait_for_hive() {
  local timeout_seconds=300
  local elapsed=0
  local delay=5

  until ss -tln | grep -qE ':9083[[:space:]]' && \
        ss -tln | grep -qE ':10000[[:space:]]' && \
        "$HIVE_HOME/bin/hive" -e 'show databases' >/dev/null 2>&1; do
    if (( elapsed >= timeout_seconds )); then
      echo "Hive was not queryable within ${timeout_seconds}s" >&2
      return 1
    fi
    echo "Waiting for queryable Hive (${elapsed}/${timeout_seconds}s)..."
    sleep "$delay"
    elapsed=$((elapsed + delay))
    (( delay < 30 )) && delay=$((delay * 2))
  done
}

exec 9>/tmp/meridian-dashboard-publish.lock
if ! flock -n 9; then
  echo "Another dashboard publish is already running; exiting successfully."
  exit 0
fi

wait_for_hive
echo "Exporting dashboard data..."
timeout 2h "$SPARK_HOME/bin/spark-shell" -i /home/chirag/Desktop/Meridian/spark/export_dashboard_data.scala

echo "Generating best-effort risk advisories..."
/home/chirag/Desktop/Meridian/.venv/bin/python /home/chirag/Desktop/Meridian/ingestion/generate_risk_advisories.py

echo "Publishing dashboard data to Supabase..."
/home/chirag/Desktop/Meridian/.venv/bin/python /home/chirag/Desktop/Meridian/ingestion/push_to_supabase.py
echo "Dashboard publish complete."