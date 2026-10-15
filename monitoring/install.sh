#!/usr/bin/env bash
set -euo pipefail

RELEASE="${RELEASE:-kube-prometheus-stack}"
NS="${NS:-monitoring}"
APP_NS="${APP_NS:-servicedesk}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${GRAFANA_ADMIN_PASSWORD:-}" ]; then
  echo "GRAFANA_ADMIN_PASSWORD is not set" >&2
  exit 1
fi

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update prometheus-community >/dev/null

helm upgrade --install "$RELEASE" prometheus-community/kube-prometheus-stack \
  --namespace "$NS" --create-namespace \
  -f "$HERE/prometheus-values.yaml" \
  -f "$HERE/grafana-values.yaml" \
  --set-string grafana.adminPassword="$GRAFANA_ADMIN_PASSWORD" \
  --timeout 15m --wait

kubectl wait --for=condition=Established --timeout=120s \
  crd/servicemonitors.monitoring.coreos.com \
  crd/prometheusrules.monitoring.coreos.com

kubectl create configmap servicedesk-grafana-dashboard \
  --from-file=servicedesk-app-metrics.json="$HERE/grafana-dashboard-servicedesk.json" \
  -n "$NS" --dry-run=client -o yaml \
  | kubectl label --local -f - grafana_dashboard=1 --dry-run=client -o yaml \
  | kubectl annotate --local -f - grafana_folder=ServiceDesk --dry-run=client -o yaml \
  | kubectl apply -f -

kubectl rollout status deploy/"$RELEASE"-grafana -n "$NS" --timeout=300s

echo "monitoring stack ready in namespace $NS"
echo "prometheus NodePort 30250, grafana NodePort 30251"
echo "application namespace expected for scraping: $APP_NS"
