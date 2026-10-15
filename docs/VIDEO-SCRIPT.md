# Recorded walkthrough — script

Target length **10–12 minutes**. Written to satisfy M10's "recorded walkthrough if remote", and to
touch every module the rubric scores, in the order a grader reads them.

Each section gives the spoken line and the exact command or click. Say the number out loud wherever
one appears — a figure read aloud is what separates a demo from a slideshow.

---

## Before you hit record

Run these and confirm each one, or the recording will stall mid-take.

```bash
curl https://servicedesk-backend-1qrp.onrender.com/health
curl -s -o /dev/null -w '%{http_code}\n' http://servicedesk.local:8080/
kubectl get pods -n servicedesk
helm list -n servicedesk
kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8080:80 &
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 13000:80 &
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 &
```

The hosted API must answer `{"status":"UP"}` before you start. It sleeps after fifteen minutes and
takes up to fifty seconds to wake; waking it live looks like a broken project.

Open these tabs in order, left to right, so you never hunt for one on camera:

1. `http://servicedesk.local:8080/` — the app on Kubernetes
2. The repository
3. The Actions tab
4. The container registry package page
5. `http://localhost:13000` — Grafana
6. `http://localhost:19090/targets` — Prometheus
7. A terminal, font size up, in `helpdesk-capstone/`

Close everything else. Set the terminal to a light or dark theme that survives video compression.

---

## 1 · What this is — 45 seconds

> "This is ServiceDesk, a help desk ticketing system I built for the DevOps capstone. A ticket is
> raised against a category, given a severity and a requester, assigned to somebody, and from the
> moment it is created it carries an SLA due date twenty-four hours out."

Show the running app. Point at the stat bar.

> "A support team lives and dies by two questions: what is open right now, and what is about to
> breach its SLA. The header answers both, and those numbers come from a single stats endpoint the
> console and the Grafana dashboard both read."

> "The domain is my own. The DevOps architecture follows the course reference, which the brief
> explicitly allows."

---

## 2 · The application — M1, 60 seconds

Create a ticket on camera. Fill the form, submit, watch it appear.

> "FastAPI backend, React and TypeScript console, PostgreSQL underneath. Eleven endpoints, full CRUD
> on tickets plus categories, health, readiness and metrics."

Change its status to Pending and watch the counters move.

> "Two tables with a real foreign key — tickets reference categories — so the schema needed a proper
> migration rather than a single flat table."

```bash
curl -s http://servicedesk.local:8080/api/tickets/stats
```

> "That breaching-SLA count is computed in SQL against the due date, filtered to tickets that are
> still open or pending. A resolved ticket past its due date is not a breach."

---

## 3 · Tests — M2, 60 seconds

```bash
cd backend && python -m pytest -q
```

> "Forty tests, ninety-eight percent coverage. The rubric asked for five."

Open `backend/conftest.py`.

> "The interesting part is isolation. This resolves the test database before the application is
> imported, and if it ever resolves to the same URL as the production database it raises instead of
> running. I verified that refusal path fires — the tests cannot touch real data even by accident."

---

## 4 · Containers — M4, 60 seconds

```bash
docker compose up --build -d
docker compose ps
docker run --rm --entrypoint id ghcr.io/amanyadav7015/servicedesk-backend:5041ecb
```

> "Three services, one command. The frontend is a multi-stage build — Node compiles the bundle, nginx
> serves it, and the compiler never reaches the final image. Both containers run as non-root; that is
> uid ten thousand and one, not zero."

---

## 5 · The pipeline — M5, 2 minutes, the centrepiece

Open the Actions tab. Scroll the run list.

> "Every push to main runs five jobs: frontend build, backend tests, image build with scanning and
> publish, a compose smoke test, and a summary."

**Open the red run, commit `759989a`.**

> "This one matters most. I pushed a deliberately failing test. Tests went red — and look at the
> jobs below it. Build, scan and publish: skipped. Compose: skipped. Not failed. Skipped. The
> dependency graph stopped them before they ever took a runner."

Switch to the registry tab.

> "And here is the proof the gate is real rather than decorative. The registry holds an image for
> every green commit and nothing at all for the red one. A failing test did not just colour a badge
> red, it prevented an artifact from existing."

Point at the tag list.

> "Every tag is a commit SHA. There is no `latest` tag anywhere, so any running container can be
> traced back to the exact source commit that produced it."

---

## 6 · Security — M6, 90 seconds

Open the workflow file at the Trivy step.

> "Trivy scans both images and fails the build on anything high or critical."

Open `.trivyignore.yaml`.

> "This file is empty. Zero suppressions. It did not start that way — two high-severity issues in a
> web framework could not be patched because another dependency pinned it to an old range. Rather
> than suppress them I traced the constraint, upgraded the package that was holding the version
> down, and the entire Python section of the report disappeared. Fixed at the source, not filtered
> out of view."

> "The base image told the same story: the older nginx had forty-three findings, forty-one high and
> two critical. Moving one minor version and adding a package upgrade took that to zero."

---

## 7 · Kubernetes and Helm — M8, 2 minutes

```bash
kubectl get pods,svc,ingress -n servicedesk
helm list -n servicedesk
helm history servicedesk -n servicedesk
```

> "Backend and frontend each run two replicas behind ClusterIP services. One Ingress host routes
> slash to the frontend and slash-api to the backend. Eleven Helm revisions — install, scale,
> rollback, and image upgrades."

Show the app in the browser at the Ingress hostname.

> "Same application, now through the Ingress rather than a port-forward."

Then delete a pod on camera:

```bash
kubectl delete pod -n servicedesk -l app.kubernetes.io/component=backend --wait=false
kubectl get pods -n servicedesk -w
```

> "Kill a backend pod and the Deployment replaces it. The data is in PostgreSQL, so nothing is lost
> — refresh the console and the queue is still there."

---

## 8 · Observability — M9, 90 seconds

Prometheus targets tab, filtered to the application.

> "Both backend pods scraped, both up, no errors."

Grafana tab.

> "Twenty-three panels on live application metrics: request rate by handler, error ratio, latency
> percentiles. This is the application's own instrumentation, not node statistics."

Generate traffic in the terminal while the dashboard is on screen:

```bash
for i in $(seq 1 60); do curl -s -o /dev/null http://servicedesk.local:8080/api/tickets; done
```

> "Watch the request-rate panel while I send sixty requests."

---

## 9 · Infrastructure as code — M7, 60 seconds. Be straight here.

```bash
cd terraform && terraform plan
```

> "A thirty-five resource plan: VPC, four subnets across two availability zones, internet gateway,
> NAT, route tables, security groups, an EKS cluster and a managed node group."

> "I have to be straight about this module. I have no AWS account, so nothing here was ever applied
> to Amazon. The networking layer really was applied and destroyed — against LocalStack, a local
> emulator — and I have the state and the CLI verification for it. The EKS half is planned and
> validated only, because LocalStack's free edition does not implement the EKS API at all. The README
> says that in the first paragraph. I would rather lose those points than imply a cluster exists."

---

## 10 · The live change — M10, 2 minutes, finish on this

> "Last thing: a change going from my editor to the running cluster."

Edit a version string. Commit with a real message. Push.

```bash
git commit -am "Bump the API version served by the root banner"
git push
gh run watch --exit-status
```

While it runs:

> "Tests, then build and scan, then publish — tagged with this commit's SHA."

When green, show the registry page with the new tag, then:

```bash
helm upgrade servicedesk helm/servicedesk -n servicedesk --set backend.tag=<new-sha>
kubectl rollout status deploy/servicedesk-backend -n servicedesk
curl -s http://servicedesk.local:8080/ | head -c 120
```

> "New version, live in the cluster. Source commit, pipeline, scanned image, registry, rollout — one
> chain, nothing by hand."

---

## 11 · Close — 30 seconds

> "What I would do differently with more time: put the migration behind an advisory lock so two
> replicas starting against an empty database cannot race, and run the Terraform against a real AWS
> account to finish the EKS module."

> "Three bugs in this project only appeared when I deployed to a stricter host than my own cluster —
> an entrypoint that blocked as non-root, a runtime that refused to execute a binary carrying file
> capabilities, and a proxy sending the wrong Host header with no SNI. All three passed CI and ran
> fine in Kubernetes. That was the most useful thing I learned: passing your own tests is not the
> same as being portable."

---

## Recording notes

- Terminal font large enough to read at 1080p; clear scrollback between sections.
- Do not read this script aloud. Know the beats, say the numbers, let the screen carry the rest.
- If something fails on camera, say what you expected and what happened, then move on. A recovered
  failure demonstrates understanding; an edit that hides it does not.
- Say "the reference project" rather than naming it, and never imply the AWS infrastructure is live.
