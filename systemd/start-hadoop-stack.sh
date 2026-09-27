#!/usr/bin/env bash
set -Eeuo pipefail

source /home/chirag/bigdata/env.sh

wait_for() {
  local name="$1"
  local command="$2"
  local timeout_seconds="${3:-180}"
  local elapsed=0

  until eval "$command" >/dev/null 2>&1; do
    if (( elapsed >= timeout_seconds )); then
      echo "$name did not become ready within ${timeout_seconds}s" >&2
      return 1
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  echo "$name is ready"
}

start_if_needed() {
  local ready_command="$1"
  shift
  if eval "$ready_command" >/dev/null 2>&1; then
    return 0
  fi
  "$@"
}

echo "Starting HDFS..."
start_if_needed 'hdfs dfsadmin -report' "$HADOOP_HOME/sbin/start-dfs.sh"
wait_for "HDFS" 'hdfs dfsadmin -report'

echo "Starting YARN..."
start_if_needed 'curl -fsS http://localhost:8088/ws/v1/cluster/info' "$HADOOP_HOME/sbin/start-yarn.sh"
wait_for "YARN ResourceManager" 'curl -fsS http://localhost:8088/ws/v1/cluster/info'
wait_for "YARN NodeManager" 'yarn node -list 2>/dev/null | grep -q RUNNING'

echo "Starting Hive metastore (JDK 8)..."
if ! ss -tln | grep -qE ':9083[[:space:]]'; then
  "$HIVE_HOME/bin/hive" --service metastore >"$HOME/bigdata/data/hive/metastore.log" 2>&1 &
  metastore_pid=$!
else
  metastore_pid=""
fi
wait_for "Hive metastore" 'ss -tln | grep -qE ":9083[[:space:]]"'

echo "Starting HiveServer2 (JDK 8)..."
if ! ss -tln | grep -qE ':10000[[:space:]]'; then
  "$HIVE_HOME/bin/hiveserver2" >"$HOME/bigdata/data/hive/hiveserver2.log" 2>&1 &
  hiveserver_pid=$!
else
  hiveserver_pid=""
fi
wait_for "HiveServer2" 'ss -tln | grep -qE ":10000[[:space:]]"'
wait_for "queryable Hive" '"$HIVE_HOME/bin/hive" -e "show databases"'

echo "Hadoop, YARN, and Hive stack is ready."