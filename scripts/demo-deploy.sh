#!/usr/bin/env bash
set -euo pipefail

NS=servicedesk
REL=servicedesk
CHART="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/helm/servicedesk"
APP=http://servicedesk.local:8080

line() { printf '\n\033[1;36m%s\033[0m\n' "$1"; }

line "1. What the cluster is serving right now"
kubectl get deploy "${REL}-backend" -n "$NS" \
  -o jsonpath='{.spec.template.spec.containers[0].image}' | sed 's|.*:|   image tag  |'
echo
kubectl exec -n "$NS" "deploy/${REL}-backend" -c backend -- \
  python -c "import urllib.request,json;print('   version    '+json.load(urllib.request.urlopen('http://localhost:8000/'))['version'])"

line "2. Fetching the commit just pushed"
git -C "$(dirname "$CHART")/.." pull --quiet
TAG=$(git -C "$(dirname "$CHART")/.." rev-parse HEAD)
echo "   commit $TAG"
echo "   the pipeline published its images under this exact tag"

line "3. Rolling that image onto the cluster"
helm upgrade "$REL" "$CHART" -n "$NS" \
  --set backend.tag="$TAG" --set frontend.tag="$TAG" \
  | grep -E 'NAME:|REVISION:|STATUS:'

line "4. Waiting for the rollout"
kubectl rollout status "deploy/${REL}-backend"  -n "$NS" --timeout=240s
kubectl rollout status "deploy/${REL}-frontend" -n "$NS" --timeout=240s

line "5. Pods now running that image"
kubectl get pods -n "$NS" -o wide --no-headers | awk '{print "   " $1, $2, $3}'

line "6. What the cluster serves now"
kubectl get deploy "${REL}-backend" -n "$NS" \
  -o jsonpath='{.spec.template.spec.containers[0].image}' | sed 's|.*:|   image tag  |'
echo
kubectl exec -n "$NS" "deploy/${REL}-backend" -c backend -- \
  python -c "import urllib.request,json;print('   version    '+json.load(urllib.request.urlopen('http://localhost:8000/'))['version'])"
echo
line "7. And it still works, through the Ingress"
printf '   queue  '; curl -s --max-time 15 "$APP/api/tickets/stats"
echo
