#!/usr/bin/env bash
set -Eeuo pipefail

services=(
  meridian-hadoop-stack.service
  meridian-live-feed.service
  meridian-stream-consumer.service
  meridian-dashboard-publish.service
)

for service in "${services[@]}"; do
  echo "Starting ${service}..."
  systemctl --user start "$service"
done

echo "Meridian services started. Dashboard publishing completed successfully."
