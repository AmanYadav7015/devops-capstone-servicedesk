# Containers, pipeline and image scanning

This document covers three modules of the ServiceDesk capstone: how the application is containerised
(M4), how the GitHub Actions pipeline tests, builds and publishes it (M5), and how Trivy gates both
images on HIGH and CRITICAL CVEs (M6).

Everything below is captured output. Where the rubric asks for a screenshot there is terminal output
or a GitHub Actions log excerpt instead, because this environment has no screen-capture tooling. No
run id, digest, CVE or count in this file was invented; each one can be re-fetched with the `gh`,
`curl` or `trivy` command shown beside it.

| | |
| --- | --- |
| Repository | <https://github.com/AmanYadav7015/devops-capstone-servicedesk> |
| Branch | `main` |
| Workflow | `.github/workflows/ci-cd.yml`, named **CI/CD Pipeline** |
| Runner | `ubuntu-latest`, GitHub-hosted |
| Registry | `ghcr.io/amanyadav7015` |

### The three runs this document refers to

| Run | Commit | Result | What it shows |
| --- | --- | --- | --- |
| [38728468694](https://github.com/AmanYadav7015/devops-capstone-servicedesk/actions/runs/38728468694) | `b7562de` | success | the first full green pipeline |
| [38728767737](https://github.com/AmanYadav7015/devops-capstone-servicedesk/actions/runs/38728767737) | `759989a` | **failure** | the pytest gate stopping the build |
| [38728901266](https://github.com/AmanYadav7015/devops-capstone-servicedesk/actions/runs/38728901266) | `dfae50b` | success | the gate released once the failing test was removed |

All three were triggered by a push to `main`.

---

## 1. The images

### 1.1 `backend/Dockerfile`

Two stages. The builder stage creates a virtualenv at `/opt/venv` and installs
`backend/requirements.txt` into it. The runtime stage starts from a clean `python:3.12-slim`, copies
only the finished virtualenv, and never sees a compiler or a pip cache.

Three things in the runtime stage are deliberate:

- `apt-get upgrade -y` pulls the current Debian security updates into the layer rather than
  inheriting whatever the base image was built with.
- The `pip`, `setuptools` and `wheel` trees are deleted from both the system interpreter and the
  virtualenv. A running API server has no reason to install packages, and removing the installer
  also removes the packages vendored inside it. Section 5.5 shows what that is worth.
- `USER 10001:10001` is set after every `COPY --chown=10001:10001`, so the application files are
  owned by the account that runs them and nothing in `/app` is writable by a process that does not
  own it.

The container runs `alembic upgrade head` before `uvicorn`, so the schema is migrated on start. A
`HEALTHCHECK` polls `/health` with the standard library, which is what lets Compose and the pipeline
wait for readiness rather than sleeping.

`backend/.dockerignore` keeps `tests/`, `conftest.py`, `pytest.ini` and `requirements-dev.txt` out of
the image. The test suite is a build-time gate, not a runtime artefact, and `pytest`, `pytest-cov`
and `httpx` never reach production as a result.

### 1.2 `frontend/Dockerfile`

A multi-stage build exactly as the rubric asks: `node:22-alpine` runs `npm ci` and `npm run build`,
then `nginx:1.31-alpine` serves the resulting `dist/` directory. The Node toolchain, `node_modules`
and the source tree are all left behind in the build stage; only the compiled bundle is copied
forward.

Running nginx as a non-root user needs three adjustments, all in the Dockerfile so that
`frontend/nginx.conf` can stay a plain nginx config:

- `setcap cap_net_bind_service=+ep /usr/sbin/nginx` lets an unprivileged process bind port 80.
  `libcap` is added as a virtual package and deleted in the same layer.
- `/var/cache/nginx`, `/var/log/nginx`, `/var/run/nginx.pid`, `/etc/nginx/conf.d`,
  `/etc/nginx/templates` and `/usr/share/nginx/html` are chowned to `nginx:nginx`.
- `USER nginx` is uid 101 in the official image.

Keeping port 80 rather than moving to 8080 matters: the Helm chart's frontend Service targets port 80
and the frontend Deployment probes port 80, so the capability approach keeps the chart and the
Compose stack serving from the same port.

`apk upgrade --no-cache` runs first. Section 5.4 explains what that fixes.

### 1.3 The nginx upstream is resolved lazily

`frontend/nginx.conf` is installed as `/etc/nginx/templates/default.conf.template`, not as
`conf.d/default.conf`. The official nginx entrypoint renders templates with `envsubst` before nginx
starts, and that is what makes two things possible.

The first is that the backend origin is configurable. The Dockerfile sets
`ENV BACKEND_ORIGIN="http://backend:8000"`, the template interpolates it, and any deployment that
calls its backend Service something else can override the variable instead of rebuilding the image.

The second is that the image can start at all when `backend` does not resolve. nginx resolves a
literal hostname in `proxy_pass` at config-load time and refuses to start if DNS fails:

```text
2026/10/15 11:31:10 [emerg] 1#1: host not found in upstream "backend" in /etc/nginx/conf.d/default.conf:22
```

That is a real failure this image hit. Putting the origin in a variable defers resolution to request
time, which requires a `resolver` directive, which the entrypoint supplies from the container's own
`/etc/resolv.conf` once `NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1` is set — the script is opt-in and
returns early without it. The rendered first line inside a running container:

```console
$ docker exec <container> head -1 /etc/nginx/conf.d/default.conf
resolver 192.168.65.7 valid=10s ipv6=off;
```

The image now serves the SPA standalone and answers 502 on `/api` rather than crash-looping:

```console
$ docker run -d -p 38080:80 ghcr.io/amanyadav7015/servicedesk-frontend:dfae50b
$ curl -s -o /dev/null -w '%{http_code}\n' http://localhost:38080/
200
$ curl -s -o /dev/null -w '%{http_code}\n' http://localhost:38080/api/tickets
502
```

Because `proxy_pass` now carries a variable, nginx no longer rewrites the URI automatically, so the
`/api/` location passes `$backend_origin$request_uri` and the single-endpoint locations are exact
matches (`location = /health`) with the path spelled out.

### 1.4 Both images run as non-root

From the green run
[38728901266](https://github.com/AmanYadav7015/devops-capstone-servicedesk/actions/runs/38728901266),
step *Prove both application images run as non-root*:

```text
backend:
uid=10001(servicedesk) gid=10001(servicedesk) groups=10001(servicedesk)
frontend:
uid=101(nginx) gid=101(nginx) groups=101(nginx),101(nginx)
```

The same check runs again in the publish job against the freshly built images, and it can be
reproduced against the published images without checking anything out:

```console
$ docker run --rm --entrypoint id ghcr.io/amanyadav7015/servicedesk-backend:dfae50b
uid=10001(servicedesk) gid=10001(servicedesk) groups=10001(servicedesk)

$ docker run --rm --entrypoint id ghcr.io/amanyadav7015/servicedesk-frontend:dfae50b
uid=101(nginx) gid=101(nginx) groups=101(nginx),101(nginx)
```

---

## 2. `docker compose up --build`

`docker-compose.yml` defines the three services the rubric asks for — `postgres`, `backend`,
`frontend` — and chains them with health conditions rather than plain `depends_on`:

- `postgres` is healthy when `pg_isready` succeeds.
- `backend` starts only once `postgres` is healthy, and is healthy when `/health` answers 200.
- `frontend` starts only once `backend` is healthy.

That ordering is why the stack comes up correctly on the first attempt instead of the backend
crash-looping while PostgreSQL finishes initialising.

Host ports are `${FRONTEND_PORT:-3000}`, `${BACKEND_PORT:-8000}` and `${POSTGRES_PORT:-5432}`. The
defaults are the ones the rubric expects; the variables exist so the stack can be brought up on a
machine where those ports are already taken.

### 2.1 The stack running in the pipeline

The pipeline has a dedicated `Docker Compose stack` job so this evidence is produced on a clean
machine on every push. From run
[38728901266](https://github.com/AmanYadav7015/devops-capstone-servicedesk/actions/runs/38728901266):

```text
$ docker compose up --build --detach --wait
$ docker compose ps
NAME                   IMAGE                                 COMMAND                  SERVICE    CREATED          STATUS                    PORTS
servicedesk-backend    capstone-servicedesk-backend:local    "sh -c 'alembic upgr…"   backend    17 seconds ago   Up 11 seconds (healthy)   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
servicedesk-frontend   capstone-servicedesk-frontend:local   "/docker-entrypoint.…"   frontend   17 seconds ago   Up 5 seconds (healthy)    0.0.0.0:3000->80/tcp, [::]:3000->80/tcp
servicedesk-postgres   postgres:16-alpine                    "docker-entrypoint.s…"   postgres   17 seconds ago   Up 16 seconds (healthy)   0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp
```

`--wait` makes the step fail if any service never reaches `healthy`, so a green job means all three
containers really did pass their health checks.

The job then drives the application over HTTP:

```text
$ curl -fsS http://localhost:8000/health
{"status":"UP"}
$ curl -fsS http://localhost:8000/ready
{"status":"READY"}

$ curl -fsS -o /dev/null -w 'frontend HTTP %{http_code}\n' http://localhost:3000/
frontend HTTP 200
$ curl -fsS http://localhost:3000/api/tickets/stats
{"total":0,"open":0,"pending":0,"resolved":0,"closed":0,"breachingSla":0}
```

Every request after this point goes to port 3000, which is nginx, not the API. nginx proxies `/api/`
to `http://backend:8000` over the Compose network, so these results prove frontend-to-backend service
discovery works:

```text
created category id=5
duplicate category name -> HTTP 409
created ticket id=1
unknown ticket -> HTTP 404
{"total":1,"open":0,"pending":0,"resolved":1,"closed":0,"breachingSla":0}
```

Four endpoints and four distinct outcomes in that transcript: a 201 create, the 409 the contract
promises on a duplicate category name, a PUT that moved the ticket to `RESOLVED` (visible in the
stats line, where `resolved` is 1 and `open` is 0), and the 404 for a ticket id that does not exist.
The error branches are asserted deliberately — a smoke test that only ever exercises the happy path
cannot tell a working API from one that returns 200 to everything.

The last step reads the rows straight out of PostgreSQL to prove the writes reached the database
rather than some in-memory store:

```text
$ docker compose exec -T postgres psql -U servicedesk -d servicedesk -c 'select id, name from categories;'
 id |   name
----+----------
  1 | Hardware
  2 | Network
  3 | Access
  4 | Software
  5 | Billing
(5 rows)

$ docker compose exec -T postgres psql -U servicedesk -d servicedesk -c 'select id, subject, severity, status, requester, assignee, category_id from tickets;'
 id |           subject           | severity |  status  | requester |   assignee   | category_id
----+-----------------------------+----------+----------+-----------+--------------+-------------
  1 | VPN drops every ten minutes | HIGH     | RESOLVED | pipeline  | network-team |           5
(1 row)
```

Categories 1 to 4 were not created by the smoke test. They come from the second Alembic migration,
which is why the backend log shows two migrations running before Uvicorn binds:

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_schema, create categories and tickets tables
INFO  [alembic.runtime.migration] Running upgrade 0001_schema -> 0002_seed, seed the default service desk categories
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 2.2 Running it locally

```console
$ docker compose up --build
```

On a machine where 3000, 8000 or 5432 are already in use, override them:

```console
$ FRONTEND_PORT=3210 BACKEND_PORT=3211 POSTGRES_PORT=3212 docker compose up --build
```

---

## 3. The pipeline

`.github/workflows/ci-cd.yml`, one workflow, five jobs.

```text
backend-tests ─┬─> compose-stack ──────┬─> pipeline-summary
frontend-build ┴─> build-scan-publish ─┘
```

| Job | What it does |
| --- | --- |
| `Backend tests (pytest)` | installs `backend/requirements-dev.txt`, runs `pytest -v` with coverage, uploads `coverage.xml` |
| `Frontend build (Vite)` | `npm ci` and `npm run build`, uploads `frontend/dist` as an artifact |
| `Docker Compose stack` | the whole stack brought up and exercised, as in section 2 |
| `Build, scan and publish images` | builds both images, scans both with Trivy, pushes both to GHCR |
| `Pipeline summary` | writes the per-job results and the published image references to the run summary |

Triggers:

```yaml
on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main
  workflow_dispatch:
```

Push to `main` is the trigger the rubric asks for and is the one every run in the table above used.
The `pull_request` trigger runs the same checks on a proposed change but skips the GHCR login and
push steps, so a fork cannot publish an image. `workflow_dispatch` adds a manual button.

Permissions are `contents: read` for the workflow as a whole; only `build-scan-publish` is granted
`packages: write`, and only for as long as that job runs.

### 3.1 `pythonpath`

`pytest` invoked as a bare command does not add the current directory to `sys.path`, so
`from app.main import app` inside the tests fails with `ModuleNotFoundError: No module named 'app'`.
`backend/pytest.ini` sets `pythonpath = .`, which is why the `Run pytest` step is a plain `pytest -v`
with no `PYTHONPATH` export in front of it.

### 3.2 No PostgreSQL service for the test job

The pytest job declares no `services:` block. `backend/conftest.py` resolves its database in order:
`TEST_DATABASE_URL` if set, otherwise a sibling `_test` database if `DATABASE_URL` points at
PostgreSQL, otherwise a throwaway SQLite file. On the runner neither variable is set, so the suite
uses SQLite and the job needs no container at all. `conftest.py` raises rather than run if the test
URL ever equals `DATABASE_URL`, so the fallback cannot silently become the production database.

### 3.3 Why the image tag is not the application version

`backend/app/main.py` reports `version: "1.0.0"`. The image tag is the commit SHA instead. The two
are deliberately separate: a Docker tag may not contain `+`, so a SemVer build suffix such as
`1.0.0+build.42` is not a legal tag, and more importantly an application version does not change on
every commit while an image must. Tagging by SHA means every image is addressable by the exact source
that produced it.

### 3.4 The owner must be lowercased

`${{ github.repository_owner }}` is `AmanYadav7015`. A Docker reference may not contain uppercase
characters, so `ghcr.io/AmanYadav7015/servicedesk-backend` is rejected with `invalid reference format`
before the registry is ever contacted. The `Resolve image references from the commit SHA` step
lowercases it once and every later step uses the step output:

```bash
owner=$(printf '%s' "${{ github.repository_owner }}" | tr '[:upper:]' '[:lower:]')
```

---

## 4. The test gate is real

A gate that has never been seen failing is not a gate. Commit `759989a` deliberately added one test
that asserts the wrong payload:

```python
def test_health_endpoint_reports_down(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "DOWN"}
```

Run [38728767737](https://github.com/AmanYadav7015/devops-capstone-servicedesk/actions/runs/38728767737)
is the result. Job conclusions, straight from the API:

```console
$ gh run view 38728767737 --json jobs --jq '.jobs[] | "\(.name) => \(.conclusion)"'
Frontend build (Vite) => success
Backend tests (pytest) => failure
Pipeline summary => success
Build, scan and publish images => skipped
Docker Compose stack => skipped
```

The failure itself:

```text
tests/test_ci_gate_probe.py::test_health_endpoint_reports_down FAILED    [ 14%]
...
>       assert response.json() == {"status": "DOWN"}
E       AssertionError: assert {'status': 'UP'} == {'status': 'DOWN'}

tests/test_ci_gate_probe.py:8: AssertionError
FAILED tests/test_ci_gate_probe.py::test_health_endpoint_reports_down - AssertionError: assert {'status': 'UP'} == {'status': 'DOWN'}
=================== 1 failed, 40 passed, 1 warning in 0.57s ====================
```

Forty tests passed and one failed, and that one failure was enough. `build-scan-publish` and
`compose-stack` both declare `needs: [backend-tests, frontend-build]`, so they were reported
`skipped`, not `failed` — `needs:` stopped them before they ever occupied a runner. No image was
built and nothing was pushed.

The strongest confirmation is in the registry itself, which can be queried anonymously because both
packages are public. Asking GHCR directly for the red commit's manifest:

```console
$ TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:amanyadav7015/servicedesk-backend:pull" | jq -r .token)
$ curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
    https://ghcr.io/v2/amanyadav7015/servicedesk-backend/manifests/759989a9862e8ee7937a03964b148766991b5590
404
```

404 on both images. And the tag list, after all three runs had finished, contains the two green
commits and not the red one:

```console
$ curl -s -H "Authorization: Bearer $TOKEN" https://ghcr.io/v2/amanyadav7015/servicedesk-backend/tags/list
{"name":"amanyadav7015/servicedesk-backend","tags":["b7562de4074c01323eae9a736ac7b948f1471ffe","b7562de","dfae50b187964678491d99e26c49ebd7a743a3ef","dfae50b"]}
```

Two green commits, four tags. The red commit produced none.

Commit `dfae50b` removed the probe test and run
[38728901266](https://github.com/AmanYadav7015/devops-capstone-servicedesk/actions/runs/38728901266)
went green again on the same pipeline, with no change to the workflow in between:

```text
platform linux -- Python 3.12.15, pytest-8.3.4, pluggy-1.7.0
---------- coverage: platform linux, python 3.12.15-final-0 ----------
TOTAL               168      4    98%
======================== 40 passed, 1 warning in 1.10s =========================
```

The probe test is not in the tree. It existed for exactly one commit, and leaving a deliberately
failing test behind would have cost the testing module its own marks.

---

## 5. Publishing and scanning

### 5.1 The frontend really is built in the pipeline

From run [38728901266](https://github.com/AmanYadav7015/devops-capstone-servicedesk/actions/runs/38728901266),
step *Build the production bundle*:

```text
✓ 35 modules transformed.
dist/index.html                   0.85 kB │ gzip:  0.51 kB
dist/assets/index-DVGsV7X6.css    8.62 kB │ gzip:  2.43 kB
dist/assets/index-DJaHKaYy.js   236.00 kB │ gzip: 73.44 kB
✓ built in 1.21s
```

`npm run build` is `tsc --noEmit && vite build`, so a type error fails the job before a bundle is
produced. The bundle is uploaded as the `frontend-dist` artifact, and the frontend image build runs
the same Vite build again inside its own Node stage so that the image is reproducible from source
alone.

### 5.2 GHCR, tagged by commit SHA

Each image is tagged twice, with the full 40-character SHA and with the 7-character short SHA.
Neither is `latest`; the workflow never writes a `latest` tag at all, and the tag lists in section 4
show none.

The digests published by the latest green run:

```text
ghcr.io/amanyadav7015/servicedesk-backend@sha256:29423e4c9b7af48eac04c1436cca53f02d22c8436cd9edcec9d7010af71701e2
ghcr.io/amanyadav7015/servicedesk-frontend@sha256:4b24ebd52b23c8493bc4516becf6ff72aef866f70073e6dd10c31a1a18f1a02d
```

Package pages:

- <https://github.com/users/AmanYadav7015/packages/container/package/servicedesk-backend>
- <https://github.com/users/AmanYadav7015/packages/container/package/servicedesk-frontend>

### 5.3 The Trivy gate

Both images are scanned, in two passes each.

The first pass is informational and hides nothing:

```bash
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 0 --ignorefile /dev/null <image>
```

The second pass is the gate and fails the job:

```bash
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed \
  --ignorefile .trivyignore.yaml --exit-code 1 <image>
```

`--exit-code 1` is the whole gate: Trivy returns 1 when anything matching `--severity HIGH,CRITICAL`
survives the filters, a non-zero exit fails the step, the step fails the job, and the job failing
stops the push — the GHCR login and push steps sit after both gate steps in the same job, so there is
no path to the registry that goes around them.

`--ignore-unfixed` drops findings for which no patched package exists yet. The informational pass on
run `38728901266` reported for the backend:

```text
ghcr.io/amanyadav7015/servicedesk-backend:dfae50b... (debian 13.7)
Total: 44 (HIGH: 44, CRITICAL: 0)
```

Every one of those 44 is a Debian 13 base package — `util-linux`, `ncurses`, `systemd`, `perl`,
`login`, `libuuid1` — and a status breakdown shows why none of them is actionable:

```console
$ trivy image --scanners vuln --severity HIGH,CRITICAL --format json --ignorefile /dev/null <backend image> \
    | jq -r '[.Results[].Vulnerabilities // [] | .[].Status] | group_by(.) | map({(.[0]): length}) | add'
{"affected": 43, "fix_deferred": 1}
```

Not one is `fixed`. There is no newer `.deb` to install, so failing the build on them would only
teach the team to ignore the gate. Whenever Debian does ship a fix, `apt-get upgrade -y` in the
Dockerfile picks it up and `--ignore-unfixed` stops applying to it automatically. After the filter
both images report clean:

```text
- '0': Clean (no security findings detected)
```

### 5.4 One CVE, explained: the base image upgrade

The frontend image reports a clean scan today. It did not start that way, and the reason is the
clearest security lesson in this project.

The starter's base image was `nginx:1.27-alpine`. Scanned today on the same architecture the runner
uses:

```console
$ trivy image --platform linux/amd64 --scanners vuln --severity HIGH,CRITICAL --ignorefile /dev/null nginx:1.27-alpine
nginx:1.27-alpine (alpine 3.21.3)
Total: 43 (HIGH: 41, CRITICAL: 2)

$ trivy image --platform linux/amd64 --scanners vuln --severity HIGH,CRITICAL --ignorefile /dev/null nginx:1.31-alpine
nginx:1.31-alpine (alpine 3.24.2)
Total: 0
```

43 against 0, from changing one line. And unlike the backend's Debian findings, **all 43 have status
`fixed`** — a patched Alpine package already exists for every one of them. These are exactly the
findings a gate is right to block on. They concentrate in a handful of packages:

| Package | Findings | Installed | Fixed in |
| --- | --- | --- | --- |
| `libcrypto3` | 9 | 3.3.3-r0 | 3.3.7-r0 |
| `libssl3` | 9 | 3.3.3-r0 | 3.3.7-r0 |
| `libexpat` | 7 | | |
| `libpng` | 6 | | |
| `libxml2` | 6 | | |
| `c-ares`, `musl`, `musl-utils`, `nghttp2-libs`, `tiff`, `zlib` | 1 each | | |

**CVE-2026-31789 — heap buffer overflow in OpenSSL X.509 certificate processing.**
Severity CRITICAL, and the only CRITICAL in the set. It appears twice because Alpine ships OpenSSL as
two packages, `libcrypto3` and `libssl3`, both installed at `3.3.3-r0` and both fixed in `3.3.7-r0`.
Processing a large X.509 certificate can overflow a heap buffer on 32-bit systems. The practical
exposure in this image is small — this nginx terminates no TLS, it serves a static React bundle over
plain HTTP inside the cluster and the published image runs on 64-bit hosts — but "probably
unreachable on our architecture" is not a patch, a fixed package existed, and a certificate parser
reachable from the network is precisely the component you do not want to be nine patch releases
behind on.

The fix is the base image bump plus one line at the top of the runtime stage:

```dockerfile
FROM nginx:1.31-alpine AS runtime

RUN apk upgrade --no-cache \
 && apk add --no-cache --virtual .build-deps libcap \
 ...
```

`apk upgrade` installs the current Alpine packages into the image layer instead of inheriting
whatever was current when the base image was published, so the image does not drift back as
`1.31-alpine` ages. After both changes the gate reports:

```text
│ ghcr.io/amanyadav7015/servicedesk-frontend:dfae50b... │ alpine │ 0 │
```

Zero here is the honest kind of zero: the informational pass, which applies neither
`--ignore-unfixed` nor an ignore file, also reports zero for this image. The Alpine packages in the
frontend image have no known HIGH or CRITICAL vulnerability at the time of the scan. That is a
statement about today's database, not a permanent property — Trivy's database updates daily, and a
scan next week may find something that does not exist today. The value of running it on every push
is precisely that the answer is re-asked every time.

### 5.5 What `.trivyignore.yaml` does not contain

```yaml
vulnerabilities: []
```

The ignore file is empty, and getting it there was a choice rather than a given.

The backend originally pinned `prometheus-fastapi-instrumentator==7.0.2`. Trivy flagged two fixable
HIGH findings against the `starlette` it dragged in:

| CVE | Package | Installed | Fixed in |
| --- | --- | --- | --- |
| CVE-2026-48818 | `starlette` | 0.52.1 | 1.1.0 |
| CVE-2026-54283 | `starlette` | 0.52.1 | 1.3.1 |

Starlette is not a direct dependency and the obvious culprit was the wrong one. FastAPI 0.142.2 asks
only for `starlette>=0.46.0`, with no upper bound at all — it would have accepted the fixed release.
The constraint was one level further down:

```console
$ docker run --rm --entrypoint sh <backend image> -c \
    "python -c \"import importlib.metadata as m; print(m.metadata('prometheus-fastapi-instrumentator').get_all('Requires-Dist'))\""
['starlette (>=0.30.0,<1.0.0)', ...]
```

A hard `<1.0.0` in the metrics library, which no change to FastAPI or to the Dockerfile could route
around. `prometheus-fastapi-instrumentator` 8.1.0 declares `starlette<2.0.0,>=1.0.0` instead, resolves
to starlette 1.8.0, and leaves `Instrumentator().instrument(app).expose(app, endpoint="/metrics")`
working unchanged. Raising that one pin removed both findings at the source, and the Python section
of the Trivy report disappeared entirely rather than being filtered out of it.

Suppressing the two CVEs in `.trivyignore.yaml` would have been faster and worse. A suppression with
a good `statement` and an `expired_at` date is a legitimate tool when a fix genuinely cannot be
installed — but it was reached for here before anyone had read the dependency metadata, and the fix
turned out to be a version number. The same reasoning applies to the `pip`, `setuptools` and `wheel`
deletion in the backend runtime stage: a container that cannot install packages is a container an
attacker cannot install packages into, and removing the installer removes the vendored HTTP stack
Trivy would otherwise report on. Both images now pass a gate that is suppressing nothing.

---

## 6. Getting to green: the failures on the way

The pipeline itself went green on its first run, which is only worth anything because the failures
happened locally first. They were real, and each one would have been a red run otherwise.

**1. `npm install` failed with ERESOLVE, before any build could start.**

```text
npm error While resolving: servicedesk-frontend@1.0.0
npm error Found: vite@7.1.12
npm error Could not resolve dependency:
npm error peer vite@"^8.0.0" from @vitejs/plugin-react@6.1.2
```

`@vitejs/plugin-react` 6.x requires peer `vite ^8.0.0` while `package.json` pinned vite 7.1.12 — two
pins that cannot both be satisfied. `--legacy-peer-deps` would have hidden it. The fix was
`@vitejs/plugin-react` 5.2.0, whose peer range is `^4.2.0 || ^5.0.0 || ^6.0.0 || ^7.0.0 || ^8.0.0`
and therefore survives a later move to vite 8 as well.

**2. `npm run build` then failed type-checking its own build config.**

```text
vite.config.ts(4,19): error TS2591: Cannot find name 'process'. Do you need to install type definitions for node?
```

`tsconfig.json` includes `vite.config.ts` in the type-check and the file reads `process.env`, but
`@types/node` was not a devDependency. Adding it fixed the build. Both of these were found by running
the Docker build locally rather than by pushing and waiting.

**3. The frontend container built, started, and immediately exited 1.**

```text
[emerg] 1#1: host not found in upstream "backend" in /etc/nginx/conf.d/default.conf:22
```

Covered in section 1.3. The first attempt at a fix — moving the upstream into a variable with a
`resolver` directive — produced a second, more confusing failure, because the variable was never
substituted:

```text
[emerg] 1#1: host not found in resolver "${NGINX_LOCAL_RESOLVERS}" in /etc/nginx/conf.d/default.conf:1
```

The nginx entrypoint's `15-local-resolvers.envsh` begins
`[ "${NGINX_ENTRYPOINT_LOCAL_RESOLVERS:-}" ] || return 0`. It is opt-in and silently does nothing
until that variable is set, so the template rendered with the placeholder still in it. Setting
`ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1` was the missing line.

**4. The compose smoke test failed against its own seeded data.**

```text
curl: (22) The requested URL returned error: 409
```

The smoke test created a category named `Network`, which the `0002_seed` migration had already
inserted, so the API correctly returned 409 and `curl -fsS` correctly failed the step. The test was
wrong, not the application. It now creates `Billing`, which is not seeded, and then re-posts the same
payload deliberately to assert the 409 — turning the accident into coverage of the duplicate branch.

**5. A transient `apk` failure during an image build (exit code 99)** succeeded unchanged on retry.
Worth recording only because it is the one failure in this list that was not a bug: not every red
build is a defect, and re-running before investigating is sometimes the correct first move.

---

## 7. Reproducing all of it

```console
$ docker compose up --build                     # the whole stack, section 2
$ docker compose ps                             # three services, all healthy
$ docker run --rm --entrypoint id ghcr.io/amanyadav7015/servicedesk-backend:dfae50b
$ docker run --rm --entrypoint id ghcr.io/amanyadav7015/servicedesk-frontend:dfae50b

$ cd backend && pytest -v                       # 40 tests

$ gh run list  --repo AmanYadav7015/devops-capstone-servicedesk
$ gh run view  38728767737 --repo AmanYadav7015/devops-capstone-servicedesk --log-failed
$ gh run view  38728901266 --repo AmanYadav7015/devops-capstone-servicedesk --log

$ trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed \
    --ignorefile .trivyignore.yaml --exit-code 1 \
    ghcr.io/amanyadav7015/servicedesk-backend:dfae50b187964678491d99e26c49ebd7a743a3ef

$ trivy image --platform linux/amd64 --scanners vuln --severity HIGH,CRITICAL \
    --ignorefile /dev/null nginx:1.27-alpine    # 43, section 5.4
```
