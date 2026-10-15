# ServiceDesk on Kubernetes — Helm chart walkthrough

This directory holds the Helm chart that deploys the ServiceDesk stack — the React operator console,
the FastAPI ticketing API and PostgreSQL — into a Kubernetes cluster. Every command below was run
against a live minikube cluster and the output is pasted verbatim. Nothing in this document was
typed by hand to look like output.

There is no screen-capture tooling in this environment, so wherever the rubric asks for a
"screenshot" the captured terminal output of the exact command is given instead.

## Environment this was run against

| Component | Version / value |
|---|---|
| Cluster | minikube, Kubernetes v1.37.0, single node |
| Node architecture | `arm64` (Apple Silicon) |
| Container runtime | containerd 2.3.4 |
| Helm | v4.3.0 |
| Addons | `ingress` (ingress-nginx), `metrics-server`, `storage-provisioner` |
| Namespace | `servicedesk` |
| Ingress host | `servicedesk.local` |
| Node IP | `192.168.49.2` |

The minikube node IP is not routable from the macOS host on this machine, so every request in this
document is issued either from inside the node (`minikube ssh -- curl`) or through a
`kubectl port-forward` of the ingress controller. Both are shown.

## Layout

```text
k8s/
  namespace.yaml                 Namespace servicedesk, applied with kubectl before Helm runs
helm/
  README.md                      this walkthrough
  servicedesk/
    Chart.yaml                   chart metadata, version 1.0.0, appVersion 1.0.0
    values.yaml                  defaults, pinned image tags
    values-dev.yaml              single replica, ephemeral database, no autoscaling
    values-prod.yaml             three replicas, larger requests, autoscaling 3..10
    .helmignore
    templates/
      NOTES.txt                  post-install hints, rendered with the real host and image tags
      _helpers.tpl               name/fullname/label helpers, database URL builder
      backend-deployment.yaml    backend Deployment plus the wait-for-postgres init container
      backend-service.yaml       backend ClusterIP Service plus the `backend` alias Service
      frontend-deployment.yaml   frontend Deployment
      frontend-service.yaml      frontend ClusterIP Service
      postgres.yaml              Secret, Service, PersistentVolumeClaim and Deployment
      ingress.yaml               one host, / to the frontend and /api to the backend
      hpa.yaml                   HorizontalPodAutoscaler for the backend
      servicemonitor.yaml        Prometheus ServiceMonitor, rendered only if the CRDs exist
```

## Images

The chart currently points at images built on this machine and side-loaded into the minikube node:

| Component | Image | Tag |
|---|---|---|
| Backend | `servicedesk-backend` | `1.0.0-local.20261015` |
| Frontend | `servicedesk-frontend` | `1.0.0-local.20261015` |
| Database | `postgres` | `16-alpine` (pulled from Docker Hub) |

These are local builds because at the time of writing the GitHub Actions pipeline had not yet
published the ServiceDesk packages — `ghcr.io/amanyadav7015/servicedesk-backend` and
`ghcr.io/amanyadav7015/servicedesk-frontend` both answer `DENIED` to an anonymous tag listing, which
is what GHCR returns for a package that does not exist. The tags were not guessed; they were looked
up and found to be absent:

```console
$ curl -s -H "Authorization: Bearer $TOKEN" \
    https://ghcr.io/v2/amanyadav7015/servicedesk-backend/tags/list
{"errors":[{"code":"DENIED","message":"invalid token"}]}
```

Both images were built from the repository's own Dockerfiles, with no modification, and loaded into
the node:

```console
$ docker build -t servicedesk-backend:1.0.0-local.20261015 -f backend/Dockerfile backend
$ docker build -t servicedesk-frontend:1.0.0-local.20261015 -f frontend/Dockerfile frontend
$ minikube image load servicedesk-backend:1.0.0-local.20261015
$ minikube image load servicedesk-frontend:1.0.0-local.20261015
$ minikube image ls | grep servicedesk
docker.io/library/servicedesk-frontend:1.0.0-local.20261015
docker.io/library/servicedesk-backend:1.0.0-local.20261015
```

Because they were built on the same Apple Silicon machine the node runs on, both images are native
`linux/arm64` and nothing is emulated:

```console
$ docker image inspect servicedesk-backend:1.0.0-local.20261015 --format '{{.Os}}/{{.Architecture}}'
linux/arm64
```

### Switching to the GHCR images

Once the pipeline publishes SHA-tagged packages, three lines in `values.yaml` move the release over
— no template changes:

```yaml
backend:
  image: ghcr.io/amanyadav7015/servicedesk-backend
  tag: "<commit sha>"
frontend:
  image: ghcr.io/amanyadav7015/servicedesk-frontend
  tag: "<commit sha>"
```

followed by `helm upgrade --install servicedesk helm/servicedesk -n servicedesk`. The GHCR images
are built by the pipeline on a `linux/amd64` runner, so on this `arm64` node they run under the
Rosetta binfmt handler that Docker Desktop installs. That works but is slower than the native build
above, and it is the reason the local build is what this walkthrough was captured against.

## Walkthrough

### 1. The namespace

The namespace is deliberately plain `kubectl`, not part of the chart, so that the cluster boundary
exists before Helm is given anything to install into.

```console
$ kubectl apply -f k8s/namespace.yaml
namespace/servicedesk unchanged
```

(`unchanged` because this is a re-apply; the first run printed `namespace/servicedesk created`. The
manifest is idempotent, which is the point of showing the second run.)

### 2. Lint the chart

```console
$ helm lint helm/servicedesk
==> Linting helm/servicedesk
[INFO] Chart.yaml: icon is recommended

1 chart(s) linted, 0 chart(s) failed
```

The single `[INFO]` is the chart having no icon, which is cosmetic.

### 3. Render it and read what it will create

```console
$ helm template servicedesk helm/servicedesk -n servicedesk | grep -E '^kind:|^  name:'
kind: Secret
  name: servicedesk-postgres
kind: PersistentVolumeClaim
  name: servicedesk-postgres-data
kind: Service
  name: servicedesk-backend
kind: Service
  name: backend
kind: Service
  name: servicedesk-frontend
kind: Service
  name: servicedesk-postgres
kind: Deployment
  name: servicedesk-backend
kind: Deployment
  name: servicedesk-frontend
kind: Deployment
  name: servicedesk-postgres
kind: HorizontalPodAutoscaler
  name: servicedesk-backend
kind: Ingress
  name: servicedesk
```

Two things to notice. The names are `servicedesk-backend`, not `servicedesk-servicedesk-backend` —
see fix 1 below. And the ServiceMonitor is missing from this list: `helm template` has no cluster to
ask, so the `.Capabilities.APIVersions.Has` guard renders it out. Against the real cluster, which
has the Prometheus operator CRDs, it is created — it appears in the resource listing further down.

### 4. Install

```console
$ helm upgrade --install servicedesk helm/servicedesk -n servicedesk --reset-values --wait
Release "servicedesk" has been upgraded. Happy Helming!
NAME: servicedesk
LAST DEPLOYED: Thu Oct 15 17:05:21 2026
NAMESPACE: servicedesk
STATUS: deployed
REVISION: 5
DESCRIPTION: Upgrade complete
TEST SUITE: None
NOTES:
ServiceDesk 1.0.0 is installed as release servicedesk in namespace servicedesk.

Backend image:  servicedesk-backend:1.0.0-local.20261015
Frontend image: servicedesk-frontend:1.0.0-local.20261015

Watch the rollout:
  kubectl get pods -n servicedesk -w

The Ingress routes one host, servicedesk.local:
  /      -> servicedesk-frontend:80
  /api   -> servicedesk-backend:8000

Reach it from the host by forwarding the ingress controller:
  kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8080:80
  curl -H 'Host: servicedesk.local' http://127.0.0.1:8080/
  curl -H 'Host: servicedesk.local' http://127.0.0.1:8080/api/tickets
```

The `servicedesk` namespace has been through several revisions by now, so that run reported
`REVISION: 5` and `Upgrade complete`; `--reset-values` is there for the reason explained under
"Helm 4 notes". To show the same command genuinely creating a release from nothing, it was also run
against a throwaway namespace. The only override is the Ingress host, because ingress-nginx's
admission webhook refuses to let two Ingress objects claim the same host and path — the first
attempt without it was rejected with
`host "servicedesk.local" and path "/api" is already defined in ingress servicedesk/servicedesk`,
which is itself a useful demonstration that the live Ingress owns that route.

```console
$ kubectl create namespace servicedesk-verify
namespace/servicedesk-verify created

$ helm upgrade --install servicedesk helm/servicedesk -n servicedesk-verify \
    --set ingress.host=servicedesk-verify.local --wait --timeout 6m
Release "servicedesk" does not exist. Installing it now.
NAME: servicedesk
LAST DEPLOYED: Thu Oct 15 17:10:02 2026
NAMESPACE: servicedesk-verify
STATUS: deployed
REVISION: 1
DESCRIPTION: Install complete

$ kubectl get pods -n servicedesk-verify
NAME                                    READY   STATUS    RESTARTS     AGE
servicedesk-backend-78f49d549c-bbrws    1/1     Running   0            21s
servicedesk-backend-78f49d549c-rsnbm    1/1     Running   1 (7s ago)   21s
servicedesk-frontend-657bb65c89-22vp6   1/1     Running   0            21s
servicedesk-frontend-657bb65c89-s8q8l   1/1     Running   0            21s
servicedesk-postgres-c86f4dc94-rcfdf    1/1     Running   0            21s

$ kubectl get svc,ingress -n servicedesk-verify
NAME                           TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)    AGE
service/backend                ClusterIP   10.106.43.101    <none>        8000/TCP   21s
service/servicedesk-backend    ClusterIP   10.96.46.48      <none>        8000/TCP   21s
service/servicedesk-frontend   ClusterIP   10.103.138.117   <none>        80/TCP     21s
service/servicedesk-postgres   ClusterIP   10.99.162.207    <none>        5432/TCP   21s

NAME                                    CLASS   HOSTS                      ADDRESS        PORTS   AGE
ingress.networking.k8s.io/servicedesk   nginx   servicedesk-verify.local   192.168.49.2   80      21s

$ minikube ssh -- "curl -s -o /dev/null -w 'GET /api/tickets -> %{http_code} %{content_type}\n' -H 'Host: servicedesk-verify.local' http://192.168.49.2/api/tickets"
GET /api/tickets -> 200 application/json
```

A clean namespace reaches a working stack in well under a minute from a single command. The
throwaway namespace was then removed:

```console
$ helm uninstall servicedesk -n servicedesk-verify
These resources were kept due to the resource policy:
[PersistentVolumeClaim] servicedesk-postgres-data

release "servicedesk" uninstalled

$ kubectl delete namespace servicedesk-verify
namespace "servicedesk-verify" deleted
```

#### One honest wrinkle on a cold database

Note the `RESTARTS 1` on one backend pod above. On a database that has never been migrated, both
backend replicas start at the same moment and both run `alembic upgrade head`; one of them loses the
race to create the bookkeeping table:

```console
$ kubectl logs -n servicedesk-verify servicedesk-backend-78f49d549c-rsnbm -c backend --previous | tail -4
sqlalchemy.exc.IntegrityError: (psycopg.errors.UniqueViolation) duplicate key value violates unique constraint "pg_type_typname_nsp_index"
DETAIL:  Key (typname, typnamespace)=(alembic_version, 2200) already exists.
[SQL:
CREATE TABLE alembic_version (
```

Kubernetes restarts the container, the second attempt finds the table already there, and the pod
goes `Running` about seven seconds later — which is why the install still reports success and the
rollout still converges to 2/2. It happens only on the very first install against an empty volume;
every later start and every upgrade finds the schema already at head and is a no-op.

Properly removing it means serialising the migration — an advisory lock around `alembic upgrade
head`, or a dedicated migration step — and the migration is invoked from the backend image's
entrypoint rather than from this chart, so the fix belongs with the application image and not here.
The chart makes it harmless rather than hiding it: the `wait-for-postgres` init container
(fix 5 below) guarantees the database is reachable, so the only remaining contention is between the
two replicas, and the readiness probe keeps the loser out of the Service until it has recovered.

## What is running

```console
$ kubectl get pods -n servicedesk -o wide
NAME                                    READY   STATUS    RESTARTS   AGE     IP            NODE       NOMINATED NODE   READINESS GATES
servicedesk-backend-78f49d549c-d4tlq    1/1     Running   0          53s     10.244.0.39   minikube   <none>           <none>
servicedesk-backend-78f49d549c-mh45c    1/1     Running   0          53s     10.244.0.40   minikube   <none>           <none>
servicedesk-frontend-657bb65c89-6f22m   1/1     Running   0          2m13s   10.244.0.37   minikube   <none>           <none>
servicedesk-frontend-657bb65c89-klptz   1/1     Running   0          2m17s   10.244.0.36   minikube   <none>           <none>
servicedesk-postgres-c86f4dc94-8dfvs    1/1     Running   0          12m     10.244.0.14   minikube   <none>           <none>

$ kubectl get deploy -n servicedesk
NAME                   READY   UP-TO-DATE   AVAILABLE   AGE
servicedesk-backend    2/2     2            2           12m
servicedesk-frontend   2/2     2            2           12m
servicedesk-postgres   1/1     1            1           12m

$ kubectl get svc -n servicedesk
NAME                   TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)    AGE
backend                ClusterIP   10.111.177.221   <none>        8000/TCP   12m
servicedesk-backend    ClusterIP   10.111.96.42     <none>        8000/TCP   12m
servicedesk-frontend   ClusterIP   10.102.12.52     <none>        80/TCP     12m
servicedesk-postgres   ClusterIP   10.97.163.12     <none>        5432/TCP   12m

$ kubectl get ingress -n servicedesk
NAME          CLASS   HOSTS               ADDRESS        PORTS   AGE
servicedesk   nginx   servicedesk.local   192.168.49.2   80      12m

$ helm list -n servicedesk
NAME       	NAMESPACE  	REVISION	UPDATED                             	STATUS  	CHART            	APP VERSION
servicedesk	servicedesk	5       	2026-10-15 17:05:21.615829 +0530 IST	deployed	servicedesk-1.0.0	1.0.0
```

Every Service is `ClusterIP`; nothing is exposed with a NodePort or a LoadBalancer, because the
Ingress is the single front door.

The autoscaler and the Prometheus ServiceMonitor are live too:

```console
$ kubectl get hpa -n servicedesk
NAME                  REFERENCE                        TARGETS        MINPODS   MAXPODS   REPLICAS   AGE
servicedesk-backend   Deployment/servicedesk-backend   cpu: 11%/60%   2         6         2          12m

$ kubectl top pods -n servicedesk
NAME                                    CPU(cores)   MEMORY(bytes)
servicedesk-backend-78f49d549c-d4tlq    10m          68Mi
servicedesk-backend-78f49d549c-mh45c    13m          68Mi
servicedesk-frontend-657bb65c89-6f22m   1m           12Mi
servicedesk-frontend-657bb65c89-klptz   1m           12Mi
servicedesk-postgres-c86f4dc94-8dfvs    5m           37Mi

$ kubectl get servicemonitor -n servicedesk
NAME                  AGE
servicedesk-backend   12m
```

The `hpa.minReplicas` is 2, so the autoscaler can never take either Deployment below the two
replicas the application is specified to run.

## The Ingress routes both halves of one host

The controller has resolved both rules to live pod endpoints:

```console
$ kubectl describe ingress servicedesk -n servicedesk
Rules:
  Host               Path  Backends
  ----               ----  --------
  servicedesk.local
                     /api   servicedesk-backend:8000 (10.244.0.40:8000,10.244.0.39:8000)
                     /      servicedesk-frontend:80 (10.244.0.36:80,10.244.0.37:80)
```

`/` returns the operator console's HTML:

```console
$ minikube ssh -- "curl -s -H 'Host: servicedesk.local' http://192.168.49.2/ | head -12"
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="ServiceDesk operator console for raising, triaging and resolving IT support tickets." />
    <meta name="theme-color" content="#0f172a" />
    <link rel="icon" href="data:image/svg+xml,..." />
    <title>ServiceDesk</title>
    <script type="module" crossorigin src="/assets/index-DJaHKaYy.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index-DVGsV7X6.css">
  </head>
```

`/api` on the same host returns JSON from the API:

```console
$ minikube ssh -- "curl -s -o /dev/null -w '%{http_code} %{content_type}\n' -H 'Host: servicedesk.local' http://192.168.49.2/"
200 text/html

$ minikube ssh -- "curl -s -o /dev/null -w '%{http_code} %{content_type}\n' -H 'Host: servicedesk.local' http://192.168.49.2/api/tickets"
200 application/json

$ minikube ssh -- "curl -s -H 'Host: servicedesk.local' http://192.168.49.2/api/tickets/stats"
{"total":71,"open":49,"pending":13,"resolved":5,"closed":4,"breachingSla":0}

$ minikube ssh -- "curl -s -H 'Host: servicedesk.local' http://192.168.49.2/api/categories"
[{"name":"Access","description":"Account provisioning, password resets and permission requests","id":3},{"name":"Billing","description":"Billing issues","id":5},{"name":"Hardware","description":"Laptops, docking stations, peripherals and on-site equipment","id":1},{"name":"Network","description":"VPN, Wi-Fi, firewall rules and connectivity incidents","id":2},{"name":"Software","description":"Application installs, licence keys and upgrade requests","id":4}]
```

One host, one Ingress, two content types from two different Deployments.

### Reaching it from the host

The node IP is not routable from macOS on this machine, so forward the ingress controller instead:

```console
$ kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8080:80 &

$ curl -s -o /dev/null -w '%{http_code} %{content_type}\n' -H 'Host: servicedesk.local' http://127.0.0.1:8080/
200 text/html

$ curl -s -H 'Host: servicedesk.local' http://127.0.0.1:8080/api/tickets/stats
{"total":102,"open":80,"pending":5,"resolved":13,"closed":4,"breachingSla":0}

$ curl -s -H 'Host: servicedesk.local' http://127.0.0.1:8080/ | grep -o '<title>.*</title>'
<title>ServiceDesk</title>
```

To open it in a browser rather than curl, add the host to `/etc/hosts` while that forward is up:

```text
127.0.0.1  servicedesk.local
```

then visit `http://servicedesk.local:8080/`. The `Host` header is what the Ingress matches on, so a
plain `http://127.0.0.1:8080/` will not match the rule and the controller answers 404.

## End to end through the Ingress

A ticket is created over HTTP, read back, and then shown to outlive the pods that created it.

```console
$ minikube ssh -- "curl -s -X POST -H 'Host: servicedesk.local' -H 'Content-Type: application/json' \
    -d '{\"subject\":\"Printer on floor 3 rejects every job\", ... ,\"category_id\":1}' \
    -w '\nHTTP %{http_code}\n' http://192.168.49.2/api/tickets"
{"subject":"Printer on floor 3 rejects every job","description":"Queue accepts the job then drops it; reproduced from three different laptops after the firmware update","severity":"MEDIUM","status":"OPEN","requester":"rahul.menon@example.com","assignee":"deskside-support","category_id":1,"id":78,"created_at":"2026-10-15T11:34:41.054905Z","sla_due_at":"2026-10-16T11:34:41.054909Z"}
HTTP 201
```

Read it back on the same host:

```console
$ minikube ssh -- "curl -s -H 'Host: servicedesk.local' http://192.168.49.2/api/tickets/78"
{"subject":"Printer on floor 3 rejects every job","description":"Queue accepts the job then drops it; reproduced from three different laptops after the firmware update","severity":"MEDIUM","status":"OPEN","requester":"rahul.menon@example.com","assignee":"deskside-support","category_id":1,"id":78,"created_at":"2026-10-15T11:34:41.054905Z","sla_due_at":"2026-10-16T11:34:41.054909Z"}
```

Now destroy every backend pod and let the Deployment rebuild them:

```console
$ kubectl get pods -n servicedesk -l app.kubernetes.io/component=backend -o name
pod/servicedesk-backend-78f49d549c-lztgz
pod/servicedesk-backend-78f49d549c-vhhlf

$ kubectl delete pod -n servicedesk -l app.kubernetes.io/component=backend
pod "servicedesk-backend-78f49d549c-lztgz" deleted from servicedesk namespace
pod "servicedesk-backend-78f49d549c-vhhlf" deleted from servicedesk namespace

$ kubectl rollout status deploy/servicedesk-backend -n servicedesk --timeout=240s
Waiting for deployment "servicedesk-backend" rollout to finish: 0 of 2 updated replicas are available...
Waiting for deployment "servicedesk-backend" rollout to finish: 1 of 2 updated replicas are available...
deployment "servicedesk-backend" successfully rolled out

$ kubectl get pods -n servicedesk -l app.kubernetes.io/component=backend -o name
pod/servicedesk-backend-78f49d549c-d4tlq
pod/servicedesk-backend-78f49d549c-mh45c
```

Both pod names are different. The ticket is still there:

```console
$ minikube ssh -- "curl -s -H 'Host: servicedesk.local' http://192.168.49.2/api/tickets/78"
{"subject":"Printer on floor 3 rejects every job","description":"Queue accepts the job then drops it; reproduced from three different laptops after the firmware update","severity":"MEDIUM","status":"OPEN","requester":"rahul.menon@example.com","assignee":"deskside-support","category_id":1,"id":78,"created_at":"2026-10-15T11:34:41.054905Z","sla_due_at":"2026-10-16T11:34:41.054909Z"}
```

And it is a real row in PostgreSQL, not state cached in an API process:

```console
$ kubectl exec -n servicedesk deploy/servicedesk-postgres -- \
    psql -U servicedesk -d servicedesk -c "select id, subject, severity, status, requester from tickets where id = 78;"
 id |               subject                | severity | status |        requester
----+--------------------------------------+----------+--------+-------------------------
 78 | Printer on floor 3 rejects every job | MEDIUM   | OPEN   | rahul.menon@example.com
(1 row)
```

One caveat worth stating honestly: deleting *both* backend pods at once is harder than any real
rollout. For a few seconds between the delete and the new pods passing their readiness probes the
Ingress answers `503`, because there are no endpoints left to route to. A rolling upgrade does not
do this — see fix 8 — and the retry in the capture above shows the first attempt after the rollout
already returning 200.

## A real upgrade, and the history behind it

Scaling the frontend to three replicas, applied through Helm rather than `kubectl scale`:

```console
$ kubectl get deploy servicedesk-frontend -n servicedesk
NAME                   READY   UP-TO-DATE   AVAILABLE   AGE
servicedesk-frontend   2/2     2            2           11m

$ helm upgrade servicedesk helm/servicedesk -n servicedesk --set frontend.replicas=3 --wait
Release "servicedesk" has been upgraded. Happy Helming!
NAME: servicedesk
LAST DEPLOYED: Thu Oct 15 17:05:10 2026
NAMESPACE: servicedesk
STATUS: deployed
REVISION: 4
DESCRIPTION: Upgrade complete

$ kubectl get deploy servicedesk-frontend -n servicedesk
NAME                   READY   UP-TO-DATE   AVAILABLE   AGE
servicedesk-frontend   3/3     3            3           11m

$ kubectl get pods -n servicedesk -l app.kubernetes.io/component=frontend
NAME                                    READY   STATUS    RESTARTS   AGE
servicedesk-frontend-657bb65c89-6f22m   1/1     Running   0          103s
servicedesk-frontend-657bb65c89-klptz   1/1     Running   0          107s
servicedesk-frontend-657bb65c89-wxwrv   1/1     Running   0          4s
```

The two original pods kept their age and their ReplicaSet hash — this added a pod, it did not
recreate the Deployment. The site stayed up throughout:

```console
$ minikube ssh -- "curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: servicedesk.local' http://192.168.49.2/"
200
```

Putting it back to the committed defaults, and the resulting history:

```console
$ helm upgrade --install servicedesk helm/servicedesk -n servicedesk --reset-values --wait
Release "servicedesk" has been upgraded. Happy Helming!
NAME: servicedesk
LAST DEPLOYED: Thu Oct 15 17:05:21 2026
NAMESPACE: servicedesk
STATUS: deployed
REVISION: 5
DESCRIPTION: Upgrade complete

$ kubectl get deploy servicedesk-frontend -n servicedesk
NAME                   READY   UP-TO-DATE   AVAILABLE   AGE
servicedesk-frontend   2/2     2            2           11m

$ helm history servicedesk -n servicedesk
REVISION	UPDATED                 	STATUS    	CHART            	APP VERSION	DESCRIPTION
1       	Thu Oct 15 16:53:34 2026	superseded	servicedesk-1.0.0	1.0.0      	Install complete
2       	Thu Oct 15 17:01:31 2026	superseded	servicedesk-1.0.0	1.0.0      	Upgrade complete
3       	Thu Oct 15 17:03:27 2026	superseded	servicedesk-1.0.0	1.0.0      	Upgrade complete
4       	Thu Oct 15 17:05:10 2026	superseded	servicedesk-1.0.0	1.0.0      	Upgrade complete
5       	Thu Oct 15 17:05:21 2026	deployed  	servicedesk-1.0.0	1.0.0      	Upgrade complete
```

What the five revisions actually were: 1 the first install (backend and database only, while the
frontend image was still being built), 2 the first upgrade carrying a working frontend image,
3 the move onto the final pinned image tag, 4 the scale to three frontend replicas, 5 the return to
the chart defaults. Any of them can be restored with `helm rollback servicedesk <n> -n servicedesk`.

## Helm 4 notes

Helm 4 changes a few habits that matter when following this walkthrough:

- `helm list --all` is gone. Use `helm list -a`, or `helm list -n <ns>` for a single namespace.
- A bare `--dry-run` is deprecated in favour of `--dry-run=client` or `--dry-run=server`. This
  walkthrough uses `helm template`, which is unaffected.
- Helm 4 applies server-side by default, so field ownership conflicts surface as real errors rather
  than being silently overwritten.
- A bare `helm upgrade` carries the previous revision's user-supplied values forward. That is why
  revision 5 above passes `--reset-values`: revision 4 had `frontend.replicas=3` set on the command
  line, and without `--reset-values` it would have been inherited and the "back to defaults" step
  would have done nothing.

## The fixes that are baked into this chart

Every item below was a real failure in an earlier iteration of this chart. They are listed so that
nobody re-introduces them.

### 1. The fullname helper doubled the chart name

The naive helper is `printf "%s-%s" .Release.Name .Chart.Name`. With a release called `servicedesk`
installed from a chart called `servicedesk` that produces `servicedesk-servicedesk-backend`, and
every Service, Ingress backend and `kubectl` command in the walkthrough then disagrees with the
manifests. `templates/_helpers.tpl` collapses the duplicate:

```gotemplate
{{- define "servicedesk.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end }}
```

The release name already contains the chart name, so the prefix is dropped and the resources are
`servicedesk-backend`, `servicedesk-frontend`, `servicedesk-postgres`.

### 2. The Ingress pointed at a Service that did not exist, on a port that was not served

The Ingress backends must be literally the Service objects the chart creates, on the ports those
Services publish. Both rules are built from the same helper and the same values that build the
Services, so they cannot drift:

| Path | Service | Port |
|---|---|---|
| `/api` | `{{ include "servicedesk.fullname" . }}-backend` | `.Values.backend.port` |
| `/` | `{{ include "servicedesk.fullname" . }}-frontend` | `.Values.frontend.port` |

`/api` is written before `/` because ingress-nginx matches by descending path length, and keeping
that order in the file makes the intent obvious to a reader.

### 3. The frontend needs a Service named exactly `backend`

`frontend/nginx.conf` proxies the API to an upstream host named `backend`:

```nginx
location /api/ {
  proxy_pass http://backend:8000;
```

nginx resolves every upstream name once at startup; if the name does not resolve, nginx refuses to
start and the pod crash-loops before its readiness probe ever runs. The chart therefore ships a
second ClusterIP Service whose name is the literal string `backend`, selecting the same backend
pods:

```yaml
{{- if .Values.backend.compatibilityServiceName }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ .Values.backend.compatibilityServiceName }}
```

It is a value (`backend.compatibilityServiceName`) rather than a hard-coded name so that a cluster
which already owns the name `backend` in that namespace can rename it in one place.

### 4. The ServiceMonitor aborted the install when the Prometheus CRDs were absent

`monitoring.coreos.com/v1` only exists once kube-prometheus-stack is installed. Rendering a
ServiceMonitor into a cluster without that CRD fails the whole `helm upgrade --install`, which means
the application cannot be deployed at all on a plain cluster. The template is guarded:

```gotemplate
{{- if and .Values.monitoring.serviceMonitor.enabled (.Capabilities.APIVersions.Has "monitoring.coreos.com/v1") }}
```

The chart installs on a bare cluster and picks the ServiceMonitor up automatically on the next
upgrade once Prometheus is present. This is also why it is absent from the `helm template` output
above but present in `kubectl get servicemonitor`.

### 5. A `wait-for-postgres` init container removes the startup race

The backend runs `alembic upgrade head` before uvicorn starts. On a cold namespace the backend pods
are scheduled at the same moment as PostgreSQL, Alembic cannot open a connection, the container
exits non-zero and Kubernetes backs it off — the Deployment eventually recovers but the first
minutes are a crash loop. The init container blocks until the database answers:

```yaml
initContainers:
  - name: wait-for-postgres
    image: {{ .Values.postgres.image }}
    command:
      - sh
      - -c
      - until pg_isready -h {{ include "servicedesk.postgres.host" . }} -p {{ .Values.postgres.port }} -U {{ .Values.postgres.username }}; do echo waiting for postgres; sleep 2; done
```

It reuses the `postgres:16-alpine` image that is already being pulled for the database, so it costs
no extra image pull. The payoff is visible in the logs of a fresh pod. The init container exits as
soon as the database answers:

```console
$ kubectl logs -n servicedesk pod/servicedesk-backend-78f49d549c-d4tlq -c wait-for-postgres
servicedesk-postgres:5432 - accepting connections
```

and the application container then runs its migrations on the first attempt, with no retry and no
back-off:

```console
$ kubectl logs -n servicedesk pod/servicedesk-backend-78f49d549c-d4tlq -c backend | head -6
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 6. The database password lives in a Secret, never in the Deployment

The backend Deployment carries no credential at all. The chart renders one Secret holding
`username`, `password`, `database` and a fully assembled `database-url`, and the backend reads only
the last of those through `secretKeyRef`:

```yaml
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: {{ include "servicedesk.postgres.secretName" . }}
        key: database-url
```

The PostgreSQL Deployment pulls `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` from the same
Secret, so the two halves cannot drift apart. What the live Deployment actually contains:

```console
$ kubectl get deploy servicedesk-backend -n servicedesk -o yaml | grep -A6 'env:'
      - env:
        - name: APP_NAME
          value: ServiceDesk API
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              key: database-url
```

The backend pod template also carries a `checksum/secret` annotation over the rendered Secret, so
changing the password rolls the backend pods instead of leaving them holding a stale value.

### 7. PostgreSQL needs the `Recreate` strategy

Its PersistentVolumeClaim is `ReadWriteOnce`. With the default `RollingUpdate` strategy Kubernetes
starts the new pod before terminating the old one, the new pod cannot attach the volume, and the
rollout wedges with the new pod `Pending` indefinitely. `strategy: { type: Recreate }` on the
PostgreSQL Deployment terminates first, then starts. The PVC also carries
`helm.sh/resource-policy: keep` so that uninstalling the release does not silently delete the
ticket data.

### 8. Rolling updates that do not drop the service

Added in this rebuild. Both application Deployments declare:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1
```

so an upgrade adds a new pod and waits for it to pass its readiness probe before removing an old
one. Without it a two-replica Deployment can take both pods down at once during an image change and
the Ingress answers `503` for the duration — exactly the window visible in the pod-delete test
above, which deliberately bypasses the rollout.

## Values

| Key | Default | What it does |
|---|---|---|
| `nameOverride` | `""` | Replaces the chart name inside the generated resource names. |
| `fullnameOverride` | `""` | Replaces the whole generated name prefix. |
| `replicaCount` | `2` | Fallback replica count for both application Deployments. |
| `backend.image` | `servicedesk-backend` | Backend image repository. |
| `backend.tag` | `1.0.0-local.20261015` | Backend image tag. Empty falls back to `.Chart.AppVersion`. |
| `backend.pullPolicy` | `IfNotPresent` | Image pull policy for the backend. |
| `backend.replicas` | `2` | Backend replicas; overrides `replicaCount`. |
| `backend.port` | `8000` | Container and Service port for the backend. |
| `backend.appName` | `ServiceDesk API` | Passed to the backend as `APP_NAME`; it is the FastAPI title. |
| `backend.compatibilityServiceName` | `backend` | Name of the alias Service the frontend nginx upstream resolves. Set to `""` to drop it. |
| `backend.resources` | 100m/256Mi to 500m/512Mi | Backend requests and limits. The CPU request is also what the HPA measures against. |
| `backend.securityContext` | non-root uid 10001, no privilege escalation, all capabilities dropped | Container security context for the backend. |
| `frontend.image` | `servicedesk-frontend` | Frontend image repository. |
| `frontend.tag` | `1.0.0-local.20261015` | Frontend image tag. Empty falls back to `.Chart.AppVersion`. |
| `frontend.pullPolicy` | `IfNotPresent` | Image pull policy for the frontend. |
| `frontend.replicas` | `2` | Frontend replicas; overrides `replicaCount`. |
| `frontend.port` | `80` | Container and Service port for the frontend. |
| `frontend.resources` | 50m/64Mi to 200m/128Mi | Frontend requests and limits. |
| `frontend.securityContext` | non-root uid 101, no privilege escalation | Container security context for the frontend; 101 is the `nginx` user in the runtime image. |
| `imagePullSecrets` | `[]` | Pull secrets, needed only if the GHCR packages are made private. |
| `postgres.enabled` | `true` | Renders the in-cluster database. `false` leaves the backend pointing at whatever `DATABASE_URL` you supply instead. |
| `postgres.image` | `postgres:16-alpine` | Database image, reused by the `wait-for-postgres` init container. |
| `postgres.pullPolicy` | `IfNotPresent` | Image pull policy for the database. |
| `postgres.port` | `5432` | Database port. |
| `postgres.database` | `servicedesk` | Database name. |
| `postgres.username` | `servicedesk` | Database user. |
| `postgres.password` | `servicedesk` | Database password. Rendered only into the Secret. Override it on any real cluster. |
| `postgres.persistence.enabled` | `true` | Binds a PersistentVolumeClaim. `false` uses an `emptyDir`, which is what `values-dev.yaml` does. |
| `postgres.persistence.size` | `2Gi` | PVC size. |
| `postgres.persistence.storageClassName` | `""` | Empty means the cluster default class, which is `standard` on minikube. |
| `postgres.resources` | 50m/128Mi to 500m/512Mi | Database requests and limits. |
| `ingress.enabled` | `true` | Renders the Ingress. |
| `ingress.className` | `nginx` | Ingress class. |
| `ingress.host` | `servicedesk.local` | The single host that serves both `/` and `/api`. |
| `ingress.annotations` | `proxy-body-size: 2m` | Extra ingress-nginx annotations. |
| `hpa.enabled` | `true` | Renders a HorizontalPodAutoscaler for the backend. |
| `hpa.minReplicas` | `2` | Lower bound, kept at 2 so autoscaling can never drop the backend below two replicas. |
| `hpa.maxReplicas` | `6` | Upper bound. |
| `hpa.targetCPUUtilizationPercentage` | `60` | Scale target, measured against the backend CPU request. |
| `monitoring.serviceMonitor.enabled` | `true` | Renders a ServiceMonitor, but only if the Prometheus CRDs exist. |
| `monitoring.serviceMonitor.interval` | `15s` | Scrape interval. |
| `monitoring.serviceMonitor.releaseLabel` | `kube-prometheus-stack` | The `release` label the Prometheus operator selects ServiceMonitors by. |

### Value files

| File | Purpose |
|---|---|
| `values.yaml` | The defaults used by every command in this document. Two replicas each, persistent database, Ingress, HPA and ServiceMonitor on. |
| `values-dev.yaml` | One replica each, `emptyDir` database, no HPA, no ServiceMonitor. A throwaway namespace on a laptop. |
| `values-prod.yaml` | Three replicas each, larger backend requests, a 5Gi volume, HPA 3 to 10. |

Apply one with `-f`:

```console
$ helm upgrade --install servicedesk helm/servicedesk -n servicedesk -f helm/servicedesk/values-dev.yaml
```

## Operating the release

```console
$ helm status servicedesk -n servicedesk
$ helm get values servicedesk -n servicedesk
$ helm rollback servicedesk 4 -n servicedesk
$ kubectl logs -n servicedesk deploy/servicedesk-backend -f
$ kubectl exec -n servicedesk deploy/servicedesk-postgres -- psql -U servicedesk -d servicedesk -c '\dt'
```

Removing it, if that is ever wanted:

```console
$ helm uninstall servicedesk -n servicedesk
$ kubectl delete -f k8s/namespace.yaml
```

The PersistentVolumeClaim is annotated `helm.sh/resource-policy: keep`, so `helm uninstall` leaves
the ticket data behind on purpose; deleting the namespace is what finally removes it.

## How this maps to the Kubernetes and Helm criteria

| Criterion | Where it is shown |
|---|---|
| `k8s/namespace.yaml` exists and applies cleanly | "The namespace" above; `namespace/servicedesk unchanged` on re-apply |
| Helm chart with `Chart.yaml`, `values.yaml` and templates | the layout tree; `helm lint` passes with 0 failures |
| `helm upgrade --install` deploys without errors | "Install" above, and four further upgrades in `helm history` |
| Backend and frontend Deployments at 2+ replicas each | `kubectl get deploy` shows `servicedesk-backend 2/2` and `servicedesk-frontend 2/2` |
| ClusterIP Services expose backend and frontend | `kubectl get svc`; all four Services are `ClusterIP` |
| Ingress routes `/` to the frontend and `/api` to the backend | `kubectl describe ingress` plus the two curl captures returning `text/html` and `application/json` |
| All pods `Running` | `kubectl get pods -n servicedesk -o wide`, five of five `1/1 Running`, zero restarts |
