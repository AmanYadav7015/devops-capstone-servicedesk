# ServiceDesk — Observability (M9)

Prometheus and Grafana for the ServiceDesk helpdesk application running on minikube.

This directory holds the Helm values, the install script and the Grafana dashboard that make the
ServiceDesk backend observable. Everything below was executed against a live cluster and the output
is pasted verbatim. Nothing in this document is reconstructed from memory.

| Item | Value |
|---|---|
| Monitoring namespace | `monitoring` |
| Application namespace | `servicedesk` |
| Chart | `prometheus-community/kube-prometheus-stack` 92.1.0 (operator v0.94.1) |
| Prometheus | NodePort **30250**, in-cluster `kube-prometheus-stack-prometheus.monitoring:9090` |
| Grafana | NodePort **30251**, in-cluster `kube-prometheus-stack-grafana.monitoring:80`, v13.2.3 |
| Host access | `kubectl port-forward` — Grafana on `127.0.0.1:13000`, Prometheus on `127.0.0.1:19090` |
| Dashboard | `ServiceDesk - Application Metrics`, uid `servicedesk-app-metrics`, 23 panels |

## Files

| File | Purpose |
|---|---|
| `prometheus-values.yaml` | kube-prometheus-stack values: Prometheus spec, NodePort, a fallback scrape job for the ServiceDesk backend, and the ServiceDesk recording and alerting rules |
| `grafana-values.yaml` | Grafana subchart values: NodePort, provisioning sidecars, default home dashboard |
| `grafana-dashboard-servicedesk.json` | The ServiceDesk application dashboard, provisioned into Grafana as a labelled ConfigMap |
| `install.sh` | Idempotent installer for the whole stack plus the dashboard ConfigMap |

## Install

```bash
export GRAFANA_ADMIN_PASSWORD='<redacted — never stored in this repository>'
./monitoring/install.sh
```

The admin password is read from the environment and passed to Helm with `--set-string`. It is never
written to any file in this repository. To read the password back out of the cluster:

```bash
kubectl get secret kube-prometheus-stack-grafana -n monitoring \
  -o jsonpath='{.data.admin-password}' | base64 -d
```

### Install this before the application chart

`install.sh` installs the Prometheus Operator, which is what registers the
`monitoring.coreos.com` CRDs. The ServiceDesk Helm chart ships a `ServiceMonitor`, so if the
operator is not in the cluster first, `helm install` of the application fails with an unknown-kind
error. The script therefore ends its Helm step with an explicit CRD wait:

```
customresourcedefinition.apiextensions.k8s.io/servicemonitors.monitoring.coreos.com condition met
customresourcedefinition.apiextensions.k8s.io/prometheusrules.monitoring.coreos.com condition met
```

Installed state:

```
$ helm list -n monitoring
NAME                 	NAMESPACE 	REVISION	UPDATED                             	STATUS  	CHART                       	APP VERSION
kube-prometheus-stack	monitoring	8       	2026-10-15 17:01:40.057149 +0530 IST	deployed	kube-prometheus-stack-92.1.0	v0.94.1

$ kubectl get pods -n monitoring
NAME                                                        READY   STATUS    RESTARTS      AGE
kube-prometheus-stack-grafana-b7d6d865f-7fzcq               3/3     Running   0             8m26s
kube-prometheus-stack-kube-state-metrics-78dc75b868-fx9kj   1/1     Running   2 (16m ago)   7d20h
kube-prometheus-stack-operator-6c5dbf9cb6-wmzpz             1/1     Running   2 (16m ago)   7d20h
kube-prometheus-stack-prometheus-node-exporter-nfjkp        1/1     Running   1 (17m ago)   7d20h
obs-toolbox                                                 1/1     Running   0             9m52s
prometheus-kube-prometheus-stack-prometheus-0               2/2     Running   2 (17m ago)   7d20h

$ kubectl get svc -n monitoring
NAME                               TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)                         AGE
kube-prometheus-stack-grafana      NodePort    10.111.143.243   <none>        80:30251/TCP                    7d20h
kube-prometheus-stack-prometheus   NodePort    10.106.187.213   <none>        9090:30250/TCP,8080:32342/TCP   7d20h
```

`obs-toolbox` is a plain `curlimages/curl` pod kept in the `monitoring` namespace. The minikube node
IP `192.168.49.2` is not routable from macOS, so every HTTP check in this document was issued from
inside the cluster through that pod. Proof that the node IP really is unreachable from the host:

```
$ curl -sS -m 4 http://192.168.49.2:30250/-/ready
curl: (28) Connection timed out after 4005 milliseconds
```

## 1. The backend `/metrics` endpoint

The backend exposes metrics through `prometheus_fastapi_instrumentator`, wired up in
`backend/app/main.py`. It was not re-implemented here; it was verified.

### Content type and exposition format

```
$ kubectl exec -n monitoring obs-toolbox -- curl -sS -o /dev/null -D - http://10.244.0.39:8000/metrics
HTTP/1.1 200 OK
date: Thu, 15 Oct 2026 11:35:02 GMT
server: uvicorn
content-length: 9861
content-type: text/plain; version=1.0.0; charset=utf-8
vary: Origin
```

`content-type: text/plain; version=1.0.0` is the Prometheus text exposition format. The body carries
the matching `# HELP` and `# TYPE` metadata:

```
# HELP http_requests_total Total number of requests by method, status and handler.
# TYPE http_requests_total counter
# HELP http_request_size_bytes Content length of incoming requests by handler. ...
# TYPE http_request_size_bytes summary
# HELP http_response_size_bytes Content length of outgoing responses by handler. ...
# TYPE http_response_size_bytes summary
# HELP http_request_duration_seconds Latency with only few buckets by handler. ...
# TYPE http_request_duration_seconds histogram
# HELP python_info Python platform information
# TYPE python_info gauge
```

Full set of metric families exposed:

```
http_request_duration_highr_seconds   histogram
http_request_duration_seconds         histogram
http_request_size_bytes               summary
http_requests_total                   counter
http_response_size_bytes              summary
process_cpu_seconds_total             counter
process_max_fds / process_open_fds    gauge
process_resident_memory_bytes         gauge
process_start_time_seconds            gauge
process_virtual_memory_bytes          gauge
python_gc_collections_total           counter
python_gc_objects_collected_total     counter
python_gc_objects_uncollectable_total counter
python_info                           gauge
```

Note the two latency histograms. `http_request_duration_seconds` is the low-resolution one that
keeps the `handler` label; its buckets are only `0.1`, `0.5`, `1.0`, `+Inf`.
`http_request_duration_highr_seconds` has many more buckets but drops `handler`. Per-endpoint
service-level objectives therefore have to be expressed on a bucket boundary that actually exists in
the low-resolution histogram, which is why the ticket-API objective below is 500 ms and not an
arbitrary number.

### A static scrape proves nothing — so here is a moving counter

A single read of `/metrics` only shows that the endpoint answers. The test below reads the counter,
sends a known and exact amount of traffic, reads the counter again, and checks that the difference
equals the traffic sent. It targets one specific pod by IP so there is no load-balancing ambiguity.

```
$ POD=servicedesk-backend-78f49d549c-d4tlq   IP=10.244.0.39

--- BEFORE ---
http_requests_total{handler="/health",method="GET",status="2xx"} = 1.0

$ kubectl exec -n monitoring obs-toolbox -- sh -c \
    'i=0; while [ $i -lt 25 ]; do curl -sS -o /dev/null http://10.244.0.39:8000/health; i=$((i+1)); done'
sent exactly 25 GET /health

--- AFTER ---
http_requests_total{handler="/health",method="GET",status="2xx"} = 26.0

DELTA = 25 (expected 25)
```

The counter moved by exactly 25. The endpoint is live, not a static fixture.

## 2. Prometheus is scraping the application

Two mechanisms point Prometheus at the backend, and both are active.

**The ServiceMonitor.** The ServiceDesk Helm chart ships
`helm/servicedesk/templates/servicemonitor.yaml`, which selects the backend Service on port `http`
at path `/metrics` every 15 s. The Prometheus spec in `prometheus-values.yaml` sets
`serviceMonitorSelector: {}` and `serviceMonitorNamespaceSelector: {}` so the operator picks up
ServiceMonitors from every namespace, including `servicedesk`.

```
$ kubectl get servicemonitor -n servicedesk
NAME                  AGE
servicedesk-backend   11m
```

**A fallback scrape job.** `prometheus-values.yaml` also defines a static `additionalScrapeConfigs`
job named `servicedesk-backend-fallback` that discovers endpoints in the `servicedesk` and
`monitoring` namespaces and keeps any Service labelled `app: servicedesk-backend`. This keeps the
application scraped even if the ServiceMonitor is removed or the operator's selectors change. It is
a deliberate duplicate: the same endpoints are scraped twice under two different `job` labels, so
any aggregation across the whole namespace must deduplicate. That is handled in the recording rules
in section 5.

### Target health — the headless equivalent of the Targets page

```
$ curl -sS 'http://kube-prometheus-stack-prometheus.monitoring:9090/api/v1/targets?state=active&scrapePool=serviceMonitor/servicedesk/servicedesk-backend/0'
```

```json
{
  "scrapePool": "serviceMonitor/servicedesk/servicedesk-backend/0",
  "scrapeUrl": "http://10.244.0.39:8000/metrics",
  "health": "up",
  "lastError": "",
  "lastScrape": "2026-10-15T11:36:00.534105462Z",
  "lastScrapeDuration": 0.005023083,
  "labels": {
    "job": "servicedesk-backend",
    "namespace": "servicedesk",
    "service": "servicedesk-backend",
    "pod": "servicedesk-backend-78f49d549c-d4tlq",
    "container": "backend",
    "endpoint": "http"
  }
}
{
  "scrapePool": "serviceMonitor/servicedesk/servicedesk-backend/0",
  "scrapeUrl": "http://10.244.0.40:8000/metrics",
  "health": "up",
  "lastError": "",
  "lastScrape": "2026-10-15T11:36:09.032256168Z",
  "lastScrapeDuration": 0.002771167,
  "labels": {
    "job": "servicedesk-backend",
    "namespace": "servicedesk",
    "service": "servicedesk-backend",
    "pod": "servicedesk-backend-78f49d549c-mh45c",
    "container": "backend",
    "endpoint": "http"
  }
}
```

Both backend replicas are `"health": "up"` with an empty `"lastError"`. The fallback job reports the
same two endpoints under `"scrapePool": "servicedesk-backend-fallback"`, also `up` with no error.

## 3. The traffic behind the numbers

The figures in section 4 are not idle-cluster noise. Known traffic was generated against the
ServiceDesk API from inside the cluster, including deliberate failures so that the error rate is
explainable rather than mysterious:

| Call | Count | Expected status |
|---|---|---|
| `POST /api/categories` (new) | 1 | 201 |
| `POST /api/categories` (existing name) | 7 | 409 |
| `POST /api/tickets` | 30 + bursts | 201 |
| `POST /api/tickets` with `category_id: 987654` | 8 + bursts | 422 |
| `GET /api/tickets` | 60 + bursts | 200 |
| `GET /api/tickets/stats` | 40 + bursts | 200 |
| `GET /api/tickets/{id}` (existing) | 40 + bursts | 200 |
| `GET /api/tickets/{id}` (absent, e.g. 999901) | 25 + bursts | **404** |
| `PUT /api/tickets/{id}` | 20 + bursts | 200 |
| `PUT /api/tickets/888800` (absent) | 10 | **404** |
| `DELETE /api/tickets/{id}` | 6 | 204 |
| `GET /health`, `GET /ready` | 40 each | 200 |

Every 4xx in the dashboards comes from one of three places: a duplicate category name (409), an
unknown `category_id` on create (422), or a ticket id that does not exist (404). There are no 5xx
responses, which is why the 5xx series is absent from the status breakdown.

Final application state after the run:

```
$ curl -sS http://servicedesk-backend.servicedesk:8000/api/tickets/stats
{"total":25,"open":3,"pending":3,"resolved":15,"closed":4,"breachingSla":0}
```

## 4. PromQL against the live Prometheus API

All of the following were issued as `GET /api/v1/query` and the values are the real returned
results.

### Scrape health

```
up{job="servicedesk-backend",namespace="servicedesk"}
```
```
{pod="servicedesk-backend-78f49d549c-mh45c", instance="10.244.0.40:8000", ...} => 1
{pod="servicedesk-backend-78f49d549c-d4tlq", instance="10.244.0.39:8000", ...} => 1
```

### Requests observed, by status class

```
sum by (status) (max by (instance,handler,method,status) (http_requests_total{namespace="servicedesk"}))
```
```
{status="2xx"} => 556
{status="4xx"} => 60
```

### Request rate

```
sum(rate(http_requests_total{job="servicedesk-backend"}[5m]))
```
```
{} => 1.0187998770460096
```

### Request rate per ServiceDesk endpoint

```
sum by (handler,method) (rate(http_requests_total{job="servicedesk-backend",handler=~"/api/(tickets|categories).*"}[5m]))
```
```
{handler="/api/tickets/{ticket_id}", method="GET"} => 0.117639
{handler="/api/tickets/stats",       method="GET"} => 0.09538200450015
{handler="/api/tickets",             method="GET"} => 0.07415644444444444
{handler="/api/categories",          method="GET"} => 0.04357
{handler="/api/tickets",             method="POST"} => 0.039213
{handler="/api/tickets/{ticket_id}", method="PUT"} => 0.013071
```

FastAPI's route template is preserved as the `handler` label, so path parameters do not explode the
cardinality — every ticket id collapses into `/api/tickets/{ticket_id}`.

### Latency quantiles

```
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_highr_seconds_bucket{job="servicedesk-backend"}[5m])))
histogram_quantile(0.50, sum by (le) (rate(http_request_duration_highr_seconds_bucket{job="servicedesk-backend"}[5m])))
```
```
p95 => 0.009607176785571502    (9.6 ms)
p50 => 0.0050563882709269495   (5.1 ms)
```

Per-endpoint, from the low-resolution histogram:

```
histogram_quantile(0.95, sum by (le,handler) (rate(http_request_duration_seconds_bucket{job="servicedesk-backend",handler=~"/api/tickets.*"}[5m])))
```
```
{handler="/api/tickets"}             => 0.095
{handler="/api/tickets/stats"}       => 0.095
{handler="/api/tickets/{ticket_id}"} => 0.095
```

All three read `0.095` because every observation falls inside the first bucket (`le="0.1"`) and
`histogram_quantile` interpolates within it. That is the honest reading of a four-bucket histogram
on a fast endpoint, not three identical measurements.

### Error rate

```
sum(rate(http_requests_total{job="servicedesk-backend",status=~"4xx|5xx"}[5m]))
/
clamp_min(sum(rate(http_requests_total{job="servicedesk-backend"}[5m])), 1e-9)
```
```
{} => 0.042800076336710034    (4.28% of requests are 4xx)
```

`clamp_min` keeps the expression from dividing by zero on an idle cluster, which would otherwise
render the panel as `NaN`.

## 5. Recording rules and alerts — the helpdesk-domain metrics

The backend exposes only generic HTTP metrics. Rather than ask for a change to `backend/`, the
domain-specific figures are derived in Prometheus itself, as a `PrometheusRule` declared through
`additionalPrometheusRulesMap` in `prometheus-values.yaml`.

```
$ kubectl get prometheusrule -n monitoring | grep servicedesk
kube-prometheus-stack-servicedesk-api-rules   8m26s
```

| Recorded series | Meaning |
|---|---|
| `servicedesk:http_requests:rate5m` | total API request rate |
| `servicedesk:http_requests_by_handler:rate5m` | request rate per endpoint and method |
| `servicedesk:http_errors:rate5m` | 4xx + 5xx request rate |
| `servicedesk:http_error_ratio:rate5m` | error share of all traffic |
| `servicedesk:http_request_latency_p95:5m` | p95 latency across the API |
| `servicedesk:ticket_api_requests:rate5m` | request rate on the ticket CRUD surface only |
| `servicedesk:ticket_api_sla_fast_ratio:5m` | share of ticket API calls served within 500 ms |
| `servicedesk:ticket_api_sla_breach_ratio:5m` | share of ticket API calls that missed the 500 ms objective |

Live values:

```
servicedesk:http_requests:rate5m           => 1.362538526984127
servicedesk:http_errors:rate5m             => 0.07189961111111112
servicedesk:http_error_ratio:rate5m        => 0.052768864650202085
servicedesk:http_request_latency_p95:5m    => 0.00960420522929393
servicedesk:ticket_api_sla_breach_ratio:5m => 0

servicedesk:ticket_api_requests:rate5m
  {handler="/api/tickets/{ticket_id}", method="GET"} => 0.20724005555555558
  {handler="/api/tickets",             method="GET"} => 0.16093183333333336
  {handler="/api/tickets/stats",       method="GET"} => 0.15720777777777778
  {handler="/api/tickets",             method="POST"} => 0.06767022222222223
  {handler="/api/tickets/{ticket_id}", method="PUT"} => 0.029605722222222224
```

A breach ratio of `0` is the correct answer here: every ticket API call in the run completed well
inside 500 ms. The rule is not inert — it is computed from `http_request_duration_seconds_bucket`
with `le="0.5"` against `http_request_duration_seconds_count`, and it would rise the moment the
ticket endpoints slowed down.

### Deduplication

Because the ServiceMonitor job and the fallback job scrape the same two pods, a naive
`sum(rate(...))` over the namespace counts everything twice. Each rule therefore collapses the
duplicate first:

```
sum(
  max by (instance, handler, method, status) (
    rate(http_requests_total{namespace="servicedesk"}[5m])
  )
)
```

Verified in a single atomic evaluation, so both halves are measured at the same instant:

```
# deduplicated total / single-job total  -> should be 1.0
sum(max by (instance,handler,method,status)(rate(http_requests_total{namespace="servicedesk"}[5m])))
/ sum(rate(http_requests_total{job="servicedesk-backend"}[5m]))
=> 1.0169672683459114

# raw total / single-job total  -> shows the duplication that is being removed
sum(rate(http_requests_total{namespace="servicedesk"}[5m]))
/ sum(rate(http_requests_total{job="servicedesk-backend"}[5m]))
=> 1.987752103811185
```

Without the `max by (...)` the aggregate is 1.99x too high; with it, 1.02x — the residual 2% is just
the two scrape pools landing on slightly different timestamps.

### Alert rules

```
$ curl -sS '.../api/v1/rules?type=alert'
  ServiceDeskBackendDown:        state=inactive health=ok
  ServiceDeskHighErrorRate:      state=inactive health=ok
  ServiceDeskTicketApiSlaBreach: state=inactive health=ok
```

All three are loaded and healthy, and all three are correctly inactive because the system is
behaving. Alertmanager is disabled in these values, so the rules evaluate but do not route anywhere.

## 6. Grafana

### It is up

```
$ kubectl exec -n monitoring obs-toolbox -- curl -sS http://kube-prometheus-stack-grafana.monitoring/api/health
{
  "database": "ok",
  "version": "13.2.3",
  "commit": "90ffed056f0884267356c12a0eeb72a022af53f1"
}
```

Reachable from the host through a port-forward:

```
$ kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 13000:80
$ curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:13000/api/health   -> 200
$ curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:13000/login        -> 200
$ curl -o /dev/null -w '%{http_code}\n' \
    http://127.0.0.1:13000/d/servicedesk-app-metrics/servicedesk-application-metrics -> 302
```

Host port 13000 is used because 3000 was already occupied by an unrelated process. The `302` on the
dashboard URL is Grafana redirecting an unauthenticated request to the login page, which is the
expected behaviour for a `curl` with no session.

Prometheus is exposed the same way on `127.0.0.1:19090`:

```
$ curl -sS http://127.0.0.1:19090/-/ready
Prometheus Server is Ready.
$ curl -sS -G http://127.0.0.1:19090/api/v1/query --data-urlencode 'query=max(up{job="servicedesk-backend"})'
{"status":"success","data":{"resultType":"vector","result":[{"metric":{},"value":[1792064080.240,"1"]}]}}
```

### The datasource is provisioned and healthy

```
$ curl -sS --netrc-file /tmp/.netrc http://kube-prometheus-stack-grafana.monitoring/api/datasources
[{"id":1,"uid":"prometheus","orgId":1,"name":"Prometheus","type":"prometheus",
  "access":"proxy","url":"http://kube-prometheus-stack-prometheus.monitoring:9090/",
  "isDefault":true,"jsonData":{"httpMethod":"POST","timeInterval":"15s"},"readOnly":true}]

$ curl -sS --netrc-file /tmp/.netrc .../api/datasources/uid/prometheus/health
{"details":{"application":"Prometheus","features":{"rulerApiEnabled":false}},
 "message":"Successfully queried the Prometheus API.","status":"OK"}
```

`readOnly: true` confirms it came from the provisioning sidecar rather than being clicked in by
hand. Credentials were supplied from a `.netrc` written into the ephemeral toolbox pod, so the
password never touched this repository.

### The dashboard is provisioned

`install.sh` packages `grafana-dashboard-servicedesk.json` into a ConfigMap labelled
`grafana_dashboard=1` and annotated `grafana_folder=ServiceDesk`; the Grafana sidecar imports it.

```
$ curl -sS --netrc-file /tmp/.netrc '.../api/search?query=ServiceDesk'
[{"uid":"eg1aqiw119zb4d","title":"ServiceDesk","type":"dash-folder", ...},
 {"uid":"servicedesk-app-metrics","title":"ServiceDesk - Application Metrics","type":"dash-db",
  "tags":["capstone","helpdesk","observability","servicedesk"],
  "url":"/d/servicedesk-app-metrics/servicedesk-application-metrics",
  "folderTitle":"ServiceDesk", ...}]

$ curl -sS --netrc-file /tmp/.netrc .../api/dashboards/uid/servicedesk-app-metrics
{
  "isFolder": false,
  "folderTitle": "ServiceDesk",
  "provisioned": true,
  "provisionedExternalId": "ServiceDesk/servicedesk-app-metrics.json",
  "slug": "servicedesk-application-metrics",
  "url": "/d/servicedesk-app-metrics/servicedesk-application-metrics",
  "version": 2
}
title: ServiceDesk - Application Metrics | uid: servicedesk-app-metrics | panels: 23
```

Panels, in four rows:

- **Service health** — scrape target up, request rate, error ratio, p95 latency, requests observed
- **HTTP traffic** — request rate by handler, request rate by status class
- **Latency** — p50/p90/p95/p99 percentiles, p95 by handler
- **Ticket API (ServiceDesk domain)** — ticket API request rate, ticket API p95, SLA breach ratio,
  ticket API error ratio, ticket writes observed, request rate by handler and method, and a panel
  driven directly by the recording rules

Two template variables: `datasource` (the Prometheus datasource) and `job`, populated from
`label_values(http_requests_total, job)` and filtered with the regex `/^servicedesk.*/` so only
ServiceDesk scrape jobs can be selected.

### Proof that a panel is actually populated

A screenshot would only show pixels. `POST /api/ds/query` is the exact endpoint a rendering Grafana
panel calls, so driving it with each panel's own query and showing the returned dataframes is
stronger evidence. Request bodies carried the panel's `expr`, `legendFormat`, `intervalMs`,
`maxDataPoints` and time range exactly as the panel sends them.

**Panel "Request rate by handler"** — `sum by (handler) (rate(http_requests_total{job="$job"}[1m]))`

```
refId A: status=200  frames=7
  labels={'handler': '/api/categories'}            points=19  nonnull=19  max=0.415928
  labels={'handler': '/api/tickets'}               points=22  nonnull=22  max=3.33339
  labels={'handler': '/api/tickets/stats'}         points=33  nonnull=33  max=2.66672
  labels={'handler': '/api/tickets/{ticket_id}'}   points=29  nonnull=29  max=1.4667
  labels={'handler': '/health'}                    points=36  nonnull=36  max=1.02225
  labels={'handler': '/metrics'}                   points=36  nonnull=36  max=0.266679
  labels={'handler': '/ready'}                     points=36  nonnull=36  max=1.11114
```

**Panel "Request rate by status class"** — `sum by (status) (rate(http_requests_total{job="$job"}[1m]))`

```
refId A: status=200  frames=2
  labels={'status': '2xx'}  points=36  nonnull=36  first=0.301858  last=0.445808  max=7.28889
  labels={'status': '4xx'}  points=17  nonnull=17  max=0.800014
```

**Panel "Latency percentiles"**

```
refId A (p50): status=200  points=36  nonnull=36  first=0.005        last=0.00504089  max=0.00526054
refId C (p95): status=200  points=36  nonnull=36  first=0.0095       last=0.00957769  max=0.00999503
```

**Panel "Error ratio (4xx + 5xx)"** — instant query, as a stat panel issues it

```
refId A: status=200  frames=1  points=1  value=0.0734119
```

**Panel "Ticket API recording rules"**

```
refId A: servicedesk:http_requests:rate5m         points=28  nonnull=28  first=0.337572  last=2.36922  max=4.632
refId B: servicedesk:http_errors:rate5m           points=20  nonnull=20  first=0.0359177 last=0.159135 max=0.300047
refId C: servicedesk:http_request_latency_p95:5m  points=28  nonnull=28  first=0.095     last=0.00960045
```

Every panel query returns `status=200` with multi-point, non-null dataframes. These panels render
with data, not with "No data".

## What could not be captured headlessly

Stated plainly, because the rubric asks for screenshots and this run produced none:

- **There is no browser screenshot of the Grafana dashboard in this repository, and none is claimed.**
  This work was done from a terminal with no browser driving the Grafana UI. The evidence offered
  instead is the `POST /api/ds/query` output above — the same API call the browser makes to fill each
  panel — plus the provisioning metadata showing the dashboard is loaded with 23 panels.
- **There is no screenshot of the Prometheus Targets page.** The `/api/v1/targets` JSON in section 2
  is the data that page renders, including `health` and `lastError` per target.
- **No image of the `/metrics` curl output.** The verbatim headers and body excerpts in section 1,
  and the moving-counter test, carry more information than an image would.

To produce the screenshots for submission, port-forward and open the pages in a browser:

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 13000:80
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090
# Grafana    http://127.0.0.1:13000/d/servicedesk-app-metrics  (login: admin)
# Prometheus http://127.0.0.1:19090/targets
```

## Known gaps and planned improvements

- **A true `servicedesk_open_tickets{severity=...}` gauge would need application code.** Open
  tickets by severity and real SLA-breach counts live in the database, not in the HTTP metrics, and
  `GET /api/tickets/stats` already computes them (`breachingSla`). Exporting them properly means
  adding a `prometheus_client.Gauge` in the backend and refreshing it on a timer or at scrape time.
  That file belongs to the application, so it was left alone. The recording rules in section 5 cover
  the request-level service-level objective instead, which is the part that can be derived from the
  series that already exist.
- **The two scrape paths are redundant by design.** Once the ServiceMonitor is considered stable,
  the `servicedesk-backend-fallback` job can be dropped from `prometheus-values.yaml`, which removes
  the need for the deduplicating `max by (...)` in every rule.
- **Alertmanager is disabled** to keep the minikube footprint small. The three alert rules load and
  evaluate but have nowhere to route. Enabling it is a one-line change in `prometheus-values.yaml`.
- **Retention is 12 hours** with no persistent volume on Prometheus, so history does not survive a
  pod restart. That is appropriate for a local demo and wrong for anything else.
- **The cluster still contains resources from a superseded earlier deployment** in another
  namespace, which appear as extra entries on the Prometheus Targets page. They are unrelated to
  ServiceDesk and every query and dashboard in this directory is scoped by
  `job=~"servicedesk.*"` or `namespace="servicedesk"` so they cannot contaminate these figures.
  They should be removed from the cluster before the demo.
