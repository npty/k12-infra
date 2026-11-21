# Onboarding a new app to the K12 rail

Worked example: `pmdr` (`npty-org/pmdr` -> `pmdr.npty.online`). Replace `<app>`, `<org>/<repo>`, `<host>`, `<port>` with yours.

## How it fits together

```text
app repo: push to main
  -> Actions `validate` (test, lint, build)
  -> Actions `publish`: docker build, push ghcr.io/<org>/<repo>:<git sha>
  -> publish commits the new sha into k12-infra apps/<app>/values.yaml   (needs K12_INFRA_TOKEN)
  -> ArgoCD (watching k12-infra, auto-sync) renders charts/web-app with that values file
  -> k3s rolls the pod; Service exposes ClusterIP (+ optional NodePort)
  -> cloudflared tunnel forwards <host> to the Service / NodePort
  -> https://<host>
```

Three repos are involved:

| Repo | Owns |
| --- | --- |
| app repo | source, `Dockerfile`, `.github/workflows/deploy.yml` |
| `npty/k12-infra` | `apps/<app>/` (chart wrapper + values), `argocd/applications/<app>.yaml` |
| `npty-org/infra` (`environments/personal`) | DNS CNAME and Cloudflare tunnel ingress route (Terraform) |

Push to `k12-infra` main = deploy. No `kubectl apply` for app workloads.

## Prerequisites

- App listens on a fixed port and binds `0.0.0.0` (Next.js standalone: `HOSTNAME=0.0.0.0 PORT=3000`).
- A health endpoint (pmdr: `/api/health`) and a `HEALTHCHECK` in the Dockerfile.
- Stateless is easiest. If you need disk, set `persistence.enabled: true` (1Gi PVC at `/data`, keep `replicaCount: 1`).
- Pick a free NodePort if the tunnel runs on the K12 host: taken so far are `30080` (sentence-gym), `30081` (rail-console), `30082` (pmdr). Use the next one (`30083`...). Skip it (ClusterIP only) if the in-cluster cloudflared routes to the Service, as article-archive and poke-hub do.

## Steps

### 1. App repo: Dockerfile + CI

1. Add a production `Dockerfile` (multi-stage, non-root, `HEALTHCHECK`). Verify locally:
   ```bash
   docker build -t <app>:local . && docker run --rm -p 127.0.0.1:3000:3000 <app>:local
   curl --fail http://127.0.0.1:3000/api/health
   ```
2. Copy `.github/workflows/deploy.yml` from `npty-org/pmdr`. Jobs: `validate` (all branches/PRs), `publish` (main only, `needs: validate`). `publish` needs `permissions: packages: write`, logs in to GHCR with `GITHUB_TOKEN`, pushes `ghcr.io/<org>/<repo>:${{ github.sha }}`, then checks out `npty/k12-infra` and runs:
   ```bash
   sed -i "s|^\(    tag:\).*|\1 ${GITHUB_SHA}|" apps/<app>/values.yaml
   ```
   Change the `IMAGE` env and the `apps/<app>` path. Note the sed pattern expects `tag:` indented 4 spaces (under `web-app: image:`).
3. Add the Actions secret `K12_INFRA_TOKEN` to the app repo (see Secrets). Without it, `publish` still pushes the image but silently skips the tag bump, so nothing deploys.
4. Immutable sha tags + `pullPolicy: IfNotPresent`. Never deploy `latest` with `IfNotPresent`.

### 2. k12-infra: wrapper chart

Create `apps/<app>/Chart.yaml`:

```yaml
apiVersion: v2
name: <app>
description: <one line>
type: application
version: 0.1.0
dependencies:
  - name: web-app
    version: 0.1.0
    repository: file://../../charts/web-app
```

Create `apps/<app>/values.yaml` (everything nested under `web-app:`):

```yaml
web-app:
  replicaCount: 1
  image:
    repository: ghcr.io/<org>/<repo>
    tag: <any existing sha for the first deploy>
    pullPolicy: IfNotPresent
  containerPort: 3000
  service:
    port: 80
    targetPort: 3000
    nodePort: 30083        # omit for ClusterIP-only
  imagePullSecrets:
    - name: ghcr-pull      # only for a private GHCR package
  host: <host>             # e.g. myapp.npty.online
  env:
    - name: NODE_ENV
      value: production
    - name: HOSTNAME
      value: 0.0.0.0
    - name: PORT
      value: "3000"
  resources:
    requests: { cpu: 50m, memory: 128Mi }
    limits: { cpu: "1", memory: 512Mi }
```

Other chart options (see `charts/web-app/values.yaml`): `secretEnv` (SealedSecret-backed env), `cronJobs`, `persistence`, `serviceAccountName`.

Keep the `tag:` line at exactly 4-space indent and on its own line, or CI's `sed` bump breaks.

### 3. k12-infra: ArgoCD Application

Create `argocd/applications/<app>.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <app>
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/npty/k12-infra.git
    targetRevision: HEAD
    path: apps/<app>
  destination:
    server: https://kubernetes.default.svc
    namespace: <app>
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions: [CreateNamespace=true]
```

Commit and push 2 and 3 together to `npty/k12-infra` main. ArgoCD creates the namespace `<app>` on first sync.

### 4. Cluster: pull secret (private GHCR only)

`CreateNamespace=true` makes the namespace, but the `ghcr-pull` secret is not in git. Until it exists the pod sits in `ImagePullBackOff`. On K12, with a PAT that has `read:packages`:

```bash
kubectl -n <app> create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io \
  --docker-username=<github-user> \
  --docker-password=<PAT read:packages>
kubectl -n <app> rollout restart deploy/<app>
```

(Existing apps use the same secret name per namespace; this step is not scripted in the repo yet.) Skip if the package is public and drop `imagePullSecrets`.

Secret env vars: do not put them in values. Create a SealedSecret in `apps/<app>/` with `kubeseal` and reference it via `web-app.secretEnv` (`secretName`, `key`, `optional: true` to avoid crash loops before the secret lands).

### 5. Public hostname (Terraform, `npty-org/infra`, `environments/personal`)

Skip if you only need in-cluster access. For a public host:

1. In `services.tf`, add a route to the `k12-managed` tunnel ingress list **before** the final `http_status:404` rule:
   ```hcl
   { hostname = "<host>", service = "http://localhost:30083" }   # NodePort from step 2
   ```
2. Add the proxied CNAME for `<host>` targeting the tunnel (copy the `pmdr.npty.online` record block).
3. `terraform plan -out=x.tfplan`, review, `terraform apply x.tfplan`. Terraform owns the whole ingress list, so never edit routes in the Cloudflare dashboard.
4. If `<host>` already points elsewhere (e.g. Vercel), the plan must show that record being replaced; confirm before applying.

### 6. Monitoring

Add an endpoint to `apps/gatus/values.yaml` (group `k12-apps`):

```yaml
- name: <App>
  group: k12-apps
  url: "https://<host>/api/health"
  interval: 60s
  conditions:
    - "[STATUS] == 200"
    - "[CERTIFICATE_EXPIRATION] > 720h"
```

(pmdr is not in Gatus yet.)

### 7. Secrets to set (once)

| Where | Name | What |
| --- | --- | --- |
| app repo, Actions secret | `K12_INFRA_TOKEN` | fine-grained PAT, **contents: write on `npty/k12-infra` only** |
| cluster, ns `<app>` | `ghcr-pull` | docker-registry secret, PAT `read:packages` |
| app repo, optional | `gh secret set K12_INFRA_TOKEN -R <org>/<repo>` | the CLI form of the first row |

Never bake API keys into the image, the workflow or `values.yaml`.

## Verify (do all, in order)

```bash
# 1. CI green and the tag bump actually ran (not skipped)
gh run list -R <org>/<repo> -L 1
gh run view <id> -R <org>/<repo> --log | grep -i "Bump image tag"   # must not say skipped

# 2. k12-infra got the sha
gh api repos/npty/k12-infra/contents/apps/<app>/values.yaml --jq .content | base64 -d | grep tag:

# 3. ArgoCD synced, pod running (on K12)
kubectl -n argocd get app <app>
kubectl -n <app> get pods

# 4. Live, cache-busted
curl -s "https://<host>/api/health?v=$(date +%s)"
curl -sI "https://<host>/?v=$(date +%s)" | head -1
```

Also confirm the live bundle really contains your change (grep a new string in `/_next/static/chunks/*.js`), since an old pod keeps answering 200.

## Release, rollback, gotchas

- Release: merge to app repo `main`. Rollout takes a few minutes after CI (ArgoCD poll + pod roll).
- Rollback: revert the tag commit in `k12-infra` (or set `tag` to an older sha). Old images stay in GHCR.
- If a deploy "succeeds" but the site is stale: the image was published but the tag bump was skipped (`K12_INFRA_TOKEN` empty). Bump `tag` by hand in `apps/<app>/values.yaml` and push.
- `selfHeal: true` reverts manual `kubectl edit`s. Change git, not the cluster.
- Hostnames are owned by Terraform, tags by CI, everything else by this repo. Do not cross those lines.
