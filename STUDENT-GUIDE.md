# ServiceDesk — student guide

Everything needed to take this repository from a cold clone to a running cluster with dashboards,
in the order you should do it. Each section is self-contained; run the commands top to bottom.

For what the system *is* and why it is built this way, read [README.md](README.md) first.

---

## 1. Prerequisites

| Tool | Version used here | Needed for | Install |
|---|---|---|---|
| Docker Engine | 29.5.2 | every section | Docker Desktop |
| Docker Compose | v5.1.3 | section 3 | bundled with Docker Desktop |
| Python | 3.12 or newer | section 4 | `brew install python@3.12` |
| Node.js | 22 or newer | section 5 | `brew install node` |
| minikube | v1.39.0 | section 6 onward | `brew install minikube` |
| kubectl | v1.37.0 | section 6 onward | `brew install kubectl` |
| Helm | v4.3.0 | sections 6 and 8 | `brew install helm` |
| Terraform | v1.16.4 | section 9 | `brew install terraform` |
| Trivy | 0.75.0 | section 10 | `brew install trivy` |
| gitleaks | 8.30.1 | section 10 | `brew install gitleaks` |
| GitHub CLI | 2.91.0 | sections 7 and 11 | `brew install gh` |

Check everything at once:

```bash
docker --version && docker compose version | head -1
python3 --version && node --version
minikube version | head -1 && kubectl version --client | head -1 && helm version --short
terraform version | head -1 && trivy --version | head -1 && gitleaks version
gh --version | head -1
```

Nothing in the local workflow needs an AWS account. Section 9 explains what that costs you.

---

## 2. First-time setup

```bash
git clone https://github.com/AmanYadav7015/devops-capstone-servicedesk.git
cd devops-capstone-servicedesk
```

Check that ports 3000, 8000 and 5432 are free — on a shared machine they often are not:

```bash
lsof -nP -iTCP:3000 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5432 -sTCP:LISTEN
```

If any of them prints a process, pick different ports when you start the stack:

```bash
export FRONTEND_PORT=3100 BACKEND_PORT=8100 POSTGRES_PORT=5433
```

No `.env` file is required. Every value has a working default, and `.env` is gitignored so a local
one can never be committed.

---

## 3. Run the stack locally

```bash
docker compose up --build
```

Wait for the three containers to report healthy. Then:

| What | Where |
|---|---|
| Operator console | <http://localhost:3000> |
| API root | <http://localhost:8000> |
| Interactive API docs | <http://localhost:8000/docs> |
| Metrics | <http://localhost:8000/metrics> |

Verify it end to end without leaving the terminal:

```bash
curl -s localhost:8000/health
curl -s localhost:8000/ready
curl -s localhost:8000/api/categories | head -c 400; echo
curl -s -X POST localhost:8000/api/tickets \
  -H 'Content-Type: application/json' \
  -d '{"subject":"Laptop will not boot after update","severity":"URGENT","requester":"j.khan","assignee":"hardware-team","category_id":1}'
echo
curl -s localhost:8000/api/tickets/stats; echo
```

Confirm the rows really reached PostgreSQL rather than an in-memory cache:

```bash
docker compose exec -T postgres psql -U servicedesk -d servicedesk -c 'select id, name from categories;'
docker compose exec -T postgres psql -U servicedesk -d servicedesk -c 'select id, subject, severity, status from tickets;'
```

Confirm both application containers run as non-root:

```bash
docker compose exec -T backend id
docker compose exec -T frontend id
```

Stop and wipe:

```bash
docker compose down --volumes --remove-orphans
```

The backend runs `alembic upgrade head` on start, so the schema and the four seeded queues
(Hardware, Network, Access, Software) are created automatically on a fresh volume.

---

## 4. Run the backend tests

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

With coverage, exactly as the pipeline runs it:

```bash
pytest -v --cov=app --cov-report=term-missing
```

The suite builds its own throwaway database and overrides the application's database dependency, so
it never reads or writes the compose database or the one in the cluster. You can have the stack from
section 3 running at the same time without interference.

Deactivate with `deactivate` when you are done. `.venv/` is gitignored.

---

## 5. Build the frontend on its own

Only needed if you are changing the UI; `docker compose up --build` does this inside the image.

```bash
cd frontend
npm install
npm run build        # type-checks with tsc, then builds with Vite into dist/
npm run dev          # http://127.0.0.1:5173
```

The dev server proxies `/api`, `/health` and `/ready` to `VITE_DEV_API_TARGET`, which defaults to
`http://127.0.0.1:8010`. If your backend is on 8000, point it there:

```bash
VITE_DEV_API_TARGET=http://127.0.0.1:8000 npm run dev
```

`VITE_API_BASE_URL` is read at *build* time and should stay empty for the container image and the
cluster, because nginx and the Ingress both serve the bundle and the API from the same origin.
`cp .env.example .env` if you want to set either locally — `.env` is gitignored.

---

## 6. Deploy to Kubernetes with Helm

### 6.1 Start the cluster

```bash
minikube start --cpus 4 --memory 6144
minikube addons enable ingress
minikube addons enable metrics-server
kubectl get nodes
```

`metrics-server` is not optional — without it the HorizontalPodAutoscaler reports `<unknown>` for
CPU and never scales.

### 6.2 Create the namespace

```bash
kubectl apply -f k8s/namespace.yaml
kubectl get ns servicedesk
```

### 6.3 Choose the images

The chart's defaults in `helm/servicedesk/values.yaml` point at locally built images, so the chart
installs on a cluster with no registry access. There are therefore two ways to deploy.

**Option A — images from GHCR, tagged with a commit (this is the real path).**

```bash
export SHA=$(git rev-parse HEAD)
gh run list --limit 5          # the run for $SHA must be green before you deploy it
```

If the run for `$SHA` has not finished, use the SHA of the last green run instead:

```bash
export SHA=$(gh run list --limit 20 --json headSha,conclusion \
  --jq 'map(select(.conclusion=="success"))[0].headSha')
echo "$SHA"
```

**Option B — images built on this machine, for working offline.**

```bash
docker build -t servicedesk-backend:local ./backend
docker build -t servicedesk-frontend:local ./frontend
minikube image load servicedesk-backend:local
minikube image load servicedesk-frontend:local
```

### 6.4 Install

Option A:

```bash
helm upgrade --install servicedesk helm/servicedesk \
  --namespace servicedesk \
  --set backend.image=ghcr.io/amanyadav7015/servicedesk-backend \
  --set frontend.image=ghcr.io/amanyadav7015/servicedesk-frontend \
  --set backend.tag="$SHA" \
  --set frontend.tag="$SHA" \
  --wait --timeout 10m
```

Option B:

```bash
helm upgrade --install servicedesk helm/servicedesk \
  --namespace servicedesk \
  --set backend.tag=local --set frontend.tag=local \
  --wait --timeout 10m
```

For a lighter single-replica install while you are iterating, add
`-f helm/servicedesk/values-dev.yaml`.

Both GHCR packages are public, so no `imagePullSecret` is needed. If you fork this and your packages
are private, create one and pass it:

```bash
kubectl create secret docker-registry ghcr -n servicedesk \
  --docker-server=ghcr.io --docker-username="$(gh api user --jq .login)" \
  --docker-password="$(gh auth token)"
helm upgrade --install servicedesk helm/servicedesk -n servicedesk --reuse-values \
  --set imagePullSecrets[0].name=ghcr
```

### 6.5 Verify

```bash
helm list -n servicedesk
kubectl get pods -n servicedesk -o wide
kubectl get svc -n servicedesk
kubectl get ingress -n servicedesk
kubectl get hpa -n servicedesk
```

You should see two backend pods, two frontend pods and one PostgreSQL pod, all `Running` and
`READY 1/1`, three `ClusterIP` services plus the short `backend` alias, and an Ingress for
`servicedesk.local` with an address.

Render the manifests without installing anything, to check a values change before applying it:

```bash
helm template servicedesk helm/servicedesk -n servicedesk | less
helm lint helm/servicedesk
```

---

## 7. Reach the application

### The macOS caveat, read this before you waste twenty minutes

On the Docker driver, minikube's node IP (`192.168.49.2`) lives inside Docker's own network and
**is not routable from the macOS host**. Adding `192.168.49.2 servicedesk.local` to `/etc/hosts`
makes `curl http://servicedesk.local` *look* correct and then hang until it times out. This is not a
problem with the Ingress, the chart or the application. Use one of the three routes below instead.

### Route A — curl from inside the node (proves the Ingress itself)

```bash
NODE_IP=$(minikube ip)
minikube ssh "curl -s -i -H 'Host: servicedesk.local' http://$NODE_IP/api/tickets/stats"
minikube ssh "curl -s -o /dev/null -w 'frontend HTTP %{http_code}\n' -H 'Host: servicedesk.local' http://$NODE_IP/"
```

Pass the whole command as **one quoted string**. `minikube ssh -- curl -H 'Host: ...'` re-splits the
arguments on the way through and the header arrives mangled, which shows up as a `400 Bad Request`
from the controller and looks like a routing fault when it is only quoting.

This is the route to use for evidence: it exercises the real ingress-nginx controller and the real
path rules, `/api` to the backend and `/` to the frontend.

### Route B — port-forward (easiest for a browser)

```bash
kubectl port-forward -n servicedesk svc/servicedesk-frontend 3000:80
```

Then open <http://localhost:3000>. The frontend's nginx proxies `/api` onward, so the console works
normally. In a second terminal, for the API directly:

```bash
kubectl port-forward -n servicedesk svc/servicedesk-backend 8000:8000
curl -s localhost:8000/api/tickets/stats
```

### Route C — `minikube tunnel` or the Ingress NodePort

```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller
# 80:30762/TCP -> curl http://$(minikube ip):30762 from inside the node, or
minikube tunnel        # keep running in its own terminal, needs sudo
```

### Quick in-cluster probe without any of the above

```bash
kubectl run netshoot --rm -it --image=nicolaka/netshoot -n servicedesk --restart=Never -- \
  curl -s http://servicedesk-backend:8000/api/tickets/stats
```

---

## 8. Metrics and dashboards

### 8.1 Install the monitoring stack

```bash
export GRAFANA_ADMIN_PASSWORD='choose-something-local'
./monitoring/install.sh
```

The script refuses to run without `GRAFANA_ADMIN_PASSWORD` — no password is stored in the
repository. It installs `kube-prometheus-stack` into the `monitoring` namespace, waits for the
operator CRDs, and loads `monitoring/grafana-dashboard-servicedesk.json` as a provisioned dashboard.

If you installed the application chart *before* the Prometheus operator CRDs existed, the
ServiceMonitor was skipped. Re-run the Helm upgrade from section 6.4 to create it:

```bash
helm upgrade --install servicedesk helm/servicedesk -n servicedesk --reuse-values
kubectl get servicemonitor -n servicedesk
```

### 8.2 Confirm the backend is exposing metrics

```bash
kubectl run netshoot --rm -it --image=nicolaka/netshoot -n servicedesk --restart=Never -- \
  curl -s http://servicedesk-backend:8000/metrics | head -40
```

Look for `http_requests_total` and `http_request_duration_seconds_bucket`.

### 8.3 Generate traffic so the panels have something to draw

```bash
kubectl port-forward -n servicedesk svc/servicedesk-backend 8000:8000 &
URL=http://localhost:8000/api/tickets COUNT=500 ./scripts/load-test.sh
```

### 8.4 Check Prometheus

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &

curl -s 'http://localhost:9090/api/v1/targets?state=active' \
  | python3 -c 'import json,sys; [print(t["labels"].get("job"), t["scrapeUrl"], t["health"]) for t in json.load(sys.stdin)["data"]["activeTargets"] if "servicedesk" in t["labels"].get("job","")]'

curl -s --data-urlencode 'query=servicedesk:http_requests:rate5m' \
  http://localhost:9090/api/v1/query | python3 -m json.tool
```

Prometheus is also on NodePort 30250 (`minikube ssh -- curl http://$(minikube ip):30250`).

### 8.5 Check Grafana

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3001:80 &
open http://localhost:3001     # user: admin, password: $GRAFANA_ADMIN_PASSWORD
```

The ServiceDesk dashboard is the configured home dashboard. From the terminal instead:

```bash
curl -s -u "admin:$GRAFANA_ADMIN_PASSWORD" http://localhost:3001/api/search?query=ServiceDesk \
  | python3 -m json.tool
```

Grafana is also on NodePort 30251.

---

## 9. Terraform

This machine has no AWS account, so there are two ways to run the stack. Read
[terraform/README.md](terraform/README.md) before you start.

### 9.1 Validate and plan offline (no account, no cost)

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -var 'skip_aws_api_checks=true' -out=offline.tfplan
terraform show -json offline.tfplan \
  | jq -r '.resource_changes[] | select(.change.actions[]=="create") | .type' | sort | uniq -c
```

`terraform.tfvars`, `*.tfstate*` and `*.tfplan` are all gitignored. Only the `.example` is tracked.

### 9.2 Apply the network half against LocalStack

```bash
docker start localstack-main || \
  docker run -d --name localstack-main -p 4566:4566 localstack/localstack

cd terraform/localstack
terraform init
terraform apply -auto-approve
terraform output

aws --endpoint-url=http://localhost:4566 ec2 describe-vpcs
aws --endpoint-url=http://localhost:4566 ec2 describe-subnets \
  --query 'Subnets[].{id:SubnetId,cidr:CidrBlock,az:AvailabilityZone,public:MapPublicIpOnLaunch}'

terraform destroy -auto-approve
```

LocalStack community implements EC2, S3, IAM and STS but **not EKS**, which is why only the network
module runs here. Captured transcripts of all of the above are in `terraform/evidence/`.

### 9.3 Against a real AWS account

```bash
cd terraform
export AWS_PROFILE=your-profile
terraform init
terraform plan
terraform apply
# ... when finished, always:
terraform destroy
```

Never commit credentials. Use `AWS_PROFILE` or environment variables, never a `.tfvars` file.

---

## 10. Security checks you can run yourself

Scan the images the same way the pipeline does:

```bash
docker build -t servicedesk-backend:local ./backend
docker build -t servicedesk-frontend:local ./frontend

trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 0 --ignorefile /dev/null servicedesk-backend:local
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --ignorefile .trivyignore.yaml --exit-code 1 servicedesk-backend:local
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --ignorefile .trivyignore.yaml --exit-code 1 servicedesk-frontend:local
```

Scan the whole git history for secrets:

```bash
gitleaks git . --redact --log-opts="--all --full-history"
```

Prove the ignore rules work and that nothing ignored was ever committed:

```bash
git check-ignore -v .env backend/__pycache__ frontend/node_modules backend/.venv
git ls-files | git check-ignore --stdin -v      # must print nothing
```

---

## 11. Watch the pipeline

```bash
gh auth status                      # must show AmanYadav7015 as the active account
gh run list --limit 5
gh run watch "$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
gh run view  "$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')"
```

To see the images a run published:

```bash
gh run view <run-id> --log | grep -E 'ghcr.io/amanyadav7015/servicedesk-(backend|frontend)@sha256'
```

A full worked example, from editing a file to the cluster serving the new build, is in
[docs/DEMO.md](docs/DEMO.md).

---

## 12. Troubleshooting exercises

Two manifests in `troubleshooting/` break on purpose. Diagnose each one before reading the answer.

### Exercise 1 — a pod that never starts

```bash
kubectl apply -f troubleshooting/broken-image.yaml
kubectl get pods -n servicedesk -l app=broken-image
kubectl describe pod -n servicedesk -l app=broken-image | tail -25
```

<details>
<summary>What you should find</summary>

`STATUS: ImagePullBackOff`, and in the events `Failed to pull image ...:does-not-exist`. The tag
does not exist in the registry. The fix is a tag that does — in this project, the SHA of a commit
whose pipeline went green. Note that the Deployment reports `READY 0/1` but the *old* ReplicaSet, if
there were one, would keep serving: a bad image rolls forward, it does not take the service down.
</details>

```bash
kubectl delete -f troubleshooting/broken-image.yaml
```

### Exercise 2 — a Service with no endpoints

```bash
kubectl apply -f troubleshooting/broken-service.yaml
kubectl get svc -n servicedesk servicedesk-broken-service
kubectl get endpoints -n servicedesk servicedesk-broken-service
kubectl describe svc -n servicedesk servicedesk-broken-service
```

<details>
<summary>What you should find</summary>

The Service exists and has a ClusterIP, but `ENDPOINTS` is `<none>`. Its selector is
`app: label-that-does-not-exist`, which matches no pod. Connections are refused immediately rather
than timing out. Compare with `kubectl get endpoints -n servicedesk servicedesk-backend`, which
lists two pod IPs. The lesson: a Service is only a label query, and a healthy-looking Service with
empty endpoints is the single most common cause of a 503 behind an Ingress.
</details>

```bash
kubectl delete -f troubleshooting/broken-service.yaml
```

### Exercise 3 — make the autoscaler react

```bash
kubectl get hpa -n servicedesk -w &
kubectl port-forward -n servicedesk svc/servicedesk-backend 8000:8000 &
URL=http://localhost:8000/api/tickets COUNT=5000 ./scripts/load-test.sh
```

Watch `TARGETS` climb past 60% and `REPLICAS` rise from 2. Scale-down is deliberately slow —
Kubernetes waits five minutes of stable low usage before removing a pod.

### Common failures and what they actually mean

| Symptom | Cause | Fix |
|---|---|---|
| `curl http://servicedesk.local` hangs on macOS | node IP is not routable from the host | use section 7 route A or B |
| Backend pods stuck in `Init:0/1` | the `wait-for-postgres` init container is still looping | `kubectl logs -n servicedesk <pod> -c wait-for-postgres`; check the postgres pod |
| `ImagePullBackOff` on a real tag | the pipeline has not published that commit yet | `gh run list`; deploy the last green SHA |
| HPA shows `<unknown>/60%` | metrics-server is missing | `minikube addons enable metrics-server` |
| `kubectl get servicemonitor` returns `No resources found` | chart installed before the Prometheus CRDs | re-run the Helm upgrade |
| Grafana panels empty | no traffic since install | run `scripts/load-test.sh`, panels use a 5 minute rate |
| `docker compose up` fails binding a port | something else owns 3000, 8000 or 5432 | set `FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_PORT` |
| `terraform plan` asks for credentials | no AWS account configured | add `-var 'skip_aws_api_checks=true'` |

---

## 13. Teardown

In reverse order of section 6 onward.

```bash
helm uninstall servicedesk -n servicedesk
kubectl delete -f troubleshooting/ --ignore-not-found
kubectl delete pvc --all -n servicedesk
kubectl delete ns servicedesk

helm uninstall kube-prometheus-stack -n monitoring
kubectl delete ns monitoring

docker compose down --volumes --remove-orphans

cd terraform/localstack && terraform destroy -auto-approve
docker stop localstack-main

minikube stop
# or, to reclaim the disk entirely:
minikube delete
```

If you ever ran section 9.3 against a real AWS account, `terraform destroy` in `terraform/` is not
optional. An EKS control plane and a NAT gateway bill by the hour whether or not anything uses them.

---

## 14. Submission checklist

Mapped one to one onto the checklist in `GRADING.md`, with the command that proves each line.

**Application**

- [ ] GitHub repository URL submitted — <https://github.com/AmanYadav7015/devops-capstone-servicedesk>
- [ ] Application runs via `docker compose up --build` — section 3
- [ ] At least 4 REST API endpoints — `curl -s localhost:8000/openapi.json | python3 -m json.tool | grep -E '"/(api)?'`
- [ ] Alembic migration file present — `ls backend/alembic/versions/`

**Testing**

- [ ] `pytest` passes — section 4, and the `backend-tests` job of any green run
- [ ] At least 5 test cases present — `cd backend && pytest --collect-only -q | tail -3`

**Docker**

- [ ] `backend/Dockerfile` builds — `docker build -t servicedesk-backend:local ./backend`
- [ ] `frontend/Dockerfile` uses a multi-stage build — `grep -c '^FROM' frontend/Dockerfile` returns 2
- [ ] Non-root user in both Dockerfiles — `docker compose exec -T backend id`, `docker compose exec -T frontend id`

**CI/CD**

- [ ] GitHub Actions workflow present — `.github/workflows/ci-cd.yml`
- [ ] Pipeline runs on push to `main` — `gh run list --limit 5`
- [ ] `pytest` runs in the pipeline — `gh run view <id> --job 'Backend tests (pytest)'`
- [ ] Images pushed to GHCR with SHA tags — [docs/DEMO.md](docs/DEMO.md)

**Security**

- [ ] Trivy scan in the pipeline — the three Trivy steps in `build-scan-publish`
- [ ] No secrets committed to git — `gitleaks git . --redact --log-opts="--all --full-history"`

**Terraform**

- [ ] `terraform plan` output submitted — `terraform/evidence/02-plan-offline.txt`
- [ ] VPC + EKS provisioned — **partial and declared as such**: VPC applied on LocalStack
      (`terraform/evidence/04`–`06`), EKS planned only (`07`), no AWS account exists (`03`)
- [ ] `terraform destroy` output submitted — `terraform/evidence/08`, `09`

**Kubernetes + Helm**

- [ ] `kubectl get pods` all Running — section 6.5
- [ ] `helm list` — `helm list -n servicedesk`
- [ ] Application accessible via the Ingress — section 7 route A

**Observability**

- [ ] `/metrics` endpoint — section 8.2
- [ ] Prometheus targets `UP` — section 8.4
- [ ] Grafana dashboard — section 8.5, with captured panel data in `monitoring/README.md`

**Documentation**

- [ ] `README.md` present — [README.md](README.md)
- [ ] Presentation or recording — walk through [docs/DEMO.md](docs/DEMO.md), which is the demo
      already captured end to end

**Before you submit**

```bash
gh auth status                                            # active account is yours
git log --oneline | wc -l                                 # at least 10
git ls-files | git check-ignore --stdin -v                # prints nothing
gitleaks git . --redact --log-opts="--all --full-history" # no leaks found
gh repo view --json isPrivate --jq '.isPrivate'           # false
```
