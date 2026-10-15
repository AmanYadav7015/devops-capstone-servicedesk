#!/usr/bin/env bash
set -euo pipefail
URL="${URL:-http://servicedesk.local/api/tickets}"
COUNT="${COUNT:-500}"
for i in $(seq 1 "$COUNT"); do curl -s "$URL" >/dev/null || true; done
echo "Load test completed: $COUNT requests against $URL"
