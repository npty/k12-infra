# Logs at a glance — Grafana dashboard (k12-infra, GitOps)

**Dashboard:** "Logs at a glance", https://grafana.npty.online/d/logs-at-a-glance
**Default time range:** last 24 hours. **Panels:** 8. **Built:** 2026-11-10, Euro chose
"errors + warnings AND business events, in one simple view" because most raw logs
are too low-level for him.

## How it is provisioned (and why UI edits do not stick)

The dashboard JSON lives here (`logs-at-a-glance.json`) and is mounted into Grafana
as a ConfigMap (`logs-at-a-glance-configmap.yaml`, label `grafana_dashboard: "1"`).
The `grafana-sc-dashboard` sidecar in the victoria-metrics stack watches ConfigMaps
with that label and mounts them under `/var/lib/grafana/dashboards/default`; the
file provider re-reads every 30s (`updateIntervalSeconds: 30`). The ArgoCD
Application `monitoring-dashboards` (in `argocd/applications/`) syncs this directory
into namespace `monitoring`.

Consequences, all intended:
- The dashboard survives a Grafana pod restart: the ConfigMap is re-mounted.
  (It does NOT live in Grafana's database, so a `kubectl delete configmap` would
  remove it; the git copy is the source of truth.)
- The dashboard is `editable: false` and the provider has `allowUiUpdates: false`:
  edits made in the Grafana UI are overwritten within ~30s. **To change a panel,
  edit `logs-at-a-glance.json` (or regenerate it with
  `~/workspace/research_notes/k12-logging-onboarding-20261110/build_dashboard.py`),
  commit, and let ArgoCD sync.** To tinker freely, duplicate it in the UI first
  (the duplicate lives in Grafana's database on the 2Gi PVC) and copy the good
  version back into git.
- Manual re-import if ever needed: Grafana > Dashboards > New > Import, paste
  `logs-at-a-glance.json`. That copy lives in the database, not in git.

## What it shows (all queries verified against VictoriaLogs, 2026-11-10)

Datasource on every panel: VictoriaLogs (`victoriametrics-logs-datasource`, uid `VictoriaLogs`).
LogsQL is the query language. Counts below are the values at build time
(2026-11-10 ~13:10 Dubai); they change as new logs arrive.

| # | Panel | LogsQL | At build time |
|---|---|---|---|
| 1 | Errors in the last 24 hours (stat) | `* \| filter "Error" \| filter NOT container:"/glance_migrated-glance-1" \| filter NOT "hoarder-chrome" \| filter NOT "helm" \| filter NOT "inspect" \| filter NOT "ACME" \| filter NOT "skipping" \| stats count()` | 9 on 2026-11-11 (was ~78,800 before the first clean-up, ~183 before the second) |
| 2 | Warnings in the last 24 hours (stat) | `* \| filter "warn" \| filter NOT kubernetes.pod_namespace:"monitoring" \| stats count()` | 2 (was 192 before the clean-up) |
| 3 | Failed checks in the last 24 hours, Gatus (stat) | `{kubernetes.pod_namespace="gatus"} \| filter "success=false" \| stats count()` | 98 |
| 4 | Errors per hour (timeseries) | same error query as panel 1, `\| stats by (_time:1h) count()` | at most 4 in any hour on 2026-11-11 |
| 5 | Top errors by app (table) | same error query as panel 1, `\| stats by (container, kubernetes.pod_namespace) count()` | Immich 4; ArgoCD 2; monitoring 1; cloudflared 1; Runtipi 1 |
| 6 | Latest error lines (logs) | same error query as panel 1, no stats | — |
| 7 | Latest warnings (logs) | `* \| filter "warn" \| filter NOT kubernetes.pod_namespace:"monitoring"` | — |
| 8 | Business events (logs, 4 targets) | (A) `* \| filter action:"heartbeat"` (B) `{kubernetes.pod_namespace="wallet-queue"}` (C) `{kubernetes.pod_namespace="gatus"} \| filter "success=false"` (D) `* \| filter service.name:poke-hub \| filter "capability.call" \| filter "completed"` | heartbeats 2; wallet-queue 7; poke-hub tool calls 26 |

## Per-app dashboards (added 2026-11-11)

One dashboard per app, same layout, same VictoriaLogs datasource, same ConfigMap
provisioning (one ConfigMap per dashboard in this directory, `grafana_dashboard: "1"`).
Each has: an "About this app" text panel (with a link back here), Errors 24h, Warnings 24h,
a health stat (failed Gatus checks for k8s apps, log-lines count for Vercel apps),
Latest log lines, and Business events for that app only. Every panel description
carries its exact LogsQL.

| App | Dashboard | Logging on 2026-11-11 |
|---|---|---|
| Sentence Gym | https://grafana.npty.online/d/app-sentence-gym | Silent, 0 lines in 7d. Running, ArgoCD Synced/Healthy, Gatus checks it every minute. |
| Rail Console | https://grafana.npty.online/d/app-rail-console | Silent, 0 lines in 7d. Same as above. |
| Article Archive | https://grafana.npty.online/d/app-article-archive | Silent, 0 lines in 7d. Same as above. |
| Manga Reader | https://grafana.npty.online/d/app-manga-reader | Silent, 0 lines in 7d. Same as above. |
| Whoop MCP Server | https://grafana.npty.online/d/app-whoop-mcp-server | Silent, 0 lines in 7d. Same as above. |
| Wallet Queue | https://grafana.npty.online/d/app-wallet-queue | 7 lines in 24h: jobs enqueued (pwa, ios-wallet-automation, smoke-test) and completed. |
| Poke Hub | https://grafana.npty.online/d/app-poke-hub | 232 lines in 24h: MCP requests + completed tool calls (26). |
| Friendly Actual Budget | https://grafana.npty.online/d/app-friendly-actual-budget | 1 line: the heartbeat. Receipt events 0 so far (see below). |

Why the 5 rail apps are silent: their startup logs predate the 2026-11-10 log-stack
rebuild (fresh PVCs, no k8s backfill) and vlagent only tails from the current offset;
the pods have not restarted since (uptimes 2–24 days on 2026-11-11), so nothing new
was captured. Silence here means "no logs captured", not "app broken" - each
per-app dashboard says so in its About panel, and Gatus is the health signal for
them until they next restart and log something.

Docker-app candidates for a per-app dashboard later (NOT built - Euro to pick):
Hoarder (logs, crawler now off), Nextcloud, Actual Budget (silent since Oct 25),
Tandoor, Immich (4 real video-encode errors on 2026-11-10), Meilisearch, Runtipi.
Building one per Docker app would be 20+ dashboards; the 8 above come first.

## What is excluded as noise (verified 2026-11-10, not guessed)

- **Glance** — excluded by container (`container:"/glance_migrated-glance-1"`). Every one of its
  ~61,500 "Error" lines/day was the identical line `Error starting file watcher, config file changes
  will require a manual restart. (creating watcher: couldn't initialize inotify: too many open files)`,
  each duplicated ~14x in VictoriaLogs. Glance was stopped 2026-11-10 at Euro's word, so no new lines
  arrive; the exclusion keeps its history out of the 24h view until it ages out. Verified: 0 Glance
  "Error" lines do NOT contain that phrase.
- **Hoarder Chrome** — excluded by message phrase (`filter NOT "hoarder-chrome"`), NOT by container.
  Every one of its ~17,200 "Error" lines/day was the identical line `[Crawler] Failed to connect to
  the browser instance, will retry in 5 secs: Error: getaddrinfo ENOTFOUND hoarder-chrome`. Verified:
  0 Hoarder "Error" lines do NOT contain that phrase. Excluding by phrase means a different Hoarder
  error in future will still show up.
- **Monitoring-namespace warnings** — excluded from panels 2 and 7 (`filter NOT
  kubernetes.pod_namespace:"monitoring"`). 190 of 192 warnings at check time were VictoriaLogs /
  vlagent / vmagent internal warnings: vlsingle "skipping log entry ... too small timestamp" (old
  Docker lines dropped by the 14-day retention, 138 lines) and startup "couldn't send a block" lines
  from the morning redeploy. Not app problems. Trade-off, stated plainly: if the monitoring stack
  itself starts warning for a new reason, this dashboard will not show it — monitoring health is
  covered by Gatus/vmalert alerts instead. The unfiltered query `* | filter "warn" | stats count()`
  is the operator check; run it in Explore when investigating the stack itself.
- **What is left after the exclusion** (24h at clean-up time): 91 errors — ArgoCD 50 (helm-template
  errors from the morning sync, 04:58–05:08), monitoring 40 (Alloy "could not inspect container info",
  tailing stopped containers), cloudflared 1. Warnings: 2, both ArgoCD warnings about unmarshalling
  this dashboard's JSON (the known, already-fixed ComparisonError — the lines are history, not live).

## Second clean-up (2026-11-11) — the last system errors

Euro approved a final pass: filter the last system errors, get real business events in.
Checked live in VictoriaLogs first (2026-11-11 ~08:00 Dubai), then re-verified through
the Grafana API after the sync. Note on method: direct VL probes through SSH lose their
double quotes (the SSH chain strips them), so multi-word phrase results from a direct
probe are unreliable - single-word filters are trustworthy, and every query below was
verified through the Grafana `/api/ds/query` path, where quotes arrive intact.

- **ArgoCD helm-template errors** — excluded by the single word `"helm"`. Scope checked:
  all 529 lines containing "helm" in 24h are in the ArgoCD namespace only, and all 57
  ArgoCD "Error" lines contain the long `helm template . --name-template <app>` line from
  the 2026-11-10 morning sync (ArgoCD still reports Synced). Narrow: a different ArgoCD
  error without the word "helm" would still show.
- **Alloy "could not inspect container info"** — excluded by the single word `"inspect"`.
  Scope checked: all 86 lines in 24h are in the monitoring namespace only (Alloy tailing
  stopped Docker containers, one line every 15 minutes per dead container id, still
  arriving live on 2026-11-11). Narrow: a different Alloy error would still show.
- **Traefik ACME failures** — excluded by the single word `"ACME"`. Scope checked: all
  43 lines in 24h are in container `/runtipi-reverse-proxy` only, all "Unable to obtain
  ACME certificate" - the known pre-existing failure (HTTP-01 never reaches Traefik
  through the Cloudflare tunnels; public HTTPS is via Cloudflare edge certs).
- **VictoriaLogs retention-drop warnings inside error lines** — excluded by the single
  word `"skipping"`. Scope checked: 106 lines in the monitoring namespace (vlsingle
  "skipping log entry ... too small timestamp", whose embedded Glance text contains the
  word "Error", which is why they polluted the error panels) plus 1 wallet-queue line
  ("smoke-test, skipping worker call" - not an Error line, so the error panels lose
  nothing there). Narrow: only lines containing "skipping".
- **Result:** filtered errors 183 → **9** in 24h (Immich video-encode permission errors 4,
  Runtipi request timeout 1, cloudflared tunnel control-stream close 1, ArgoCD dashboard-JSON
  unmarshal warnings 2, one VictoriaLogs query-parse error from a bad probe query 1 - all real,
  distinct, and worth keeping). Per-hour max is 4. Warnings unchanged at 2.
- **Trade-off, stated plainly:** these four patterns are now hidden from this dashboard.
  A genuinely new ArgoCD/Alloy/Traefik/VictoriaLogs problem that happens to contain one of
  those words would also be hidden here. The unfiltered query `* | filter "Error" | stats count()`
  is the operator check (run it in Explore when investigating), and real outages are still
  covered by Gatus (https://gatus.npty.online) and vmalert alerts.
- **Business events, panel 8:** (A) heartbeat now uses the action field
  (`* | filter action:"heartbeat"`) instead of the exact phrase "heartbeat completed" -
  the phrase also matched 2 ArgoCD warning lines that embed this dashboard's own JSON
  (its description mentions the phrase); the action filter returns exactly the 2 real
  heartbeat lines. (D) added poke-hub completed tool calls (26 in 24h, verified by tool:
  actual_budget.search_transactions 10, transaction_update 5, transaction_add 2,
  backup_to_nextcloud 2, wallos.subscriptions 1, bird_eyes 2, nextcloud 2).
  **Not added:** friendly-actual-budget receipt events - wallet-ingest-queued and
  transaction-confirmed have 0 lines in VL (checked 24h and 7d), because no real receipt
  has been saved since its OTel deploy on 2026-11-10 (the two proven receipts that morning
  happened before the deploy). The code already emits them (apps/api/src/app.ts:
  wallet-ingest-queued after a successful enqueue, transaction-confirmed on confirm paths,
  message body "<action> <status>"), so the next real PWA/iOS receipt will appear
  automatically - watch it with `* | filter service.name:friendly-actual-budget | filter NOT action:"heartbeat"`.
  No code change, no redeploy, and no fake receipt was posted.

## Bundled dashboards removed (2026-11-10)

Euro asked for ONLY "Logs at a glance" in the Grafana Dashboards list. The victoria-metrics
stack ships 43 bundled dashboards (Kubernetes / Compute Resources / Cluster / Namespace / Node /
Pod / Workload / Kubelet / Networking / API server, Node Exporter, Prometheus, VictoriaMetrics,
VictoriaLogs, Alertmanager, Grafana Overview — tags `vm-k8s-stack`, `kubernetes-mixin`, etc.).
They are provisioned by the chart (`defaultDashboards`), so deleting them in the UI would bring
them back on restart/sync. Removed properly in git: `defaultDashboards.enabled: false` in
`apps/victoria-metrics/values.yaml` (chart 0.98.1, verified with `helm show values` — the option is
`defaultDashboards.enabled`). "Logs at a glance" does not depend on any bundled dashboard (it only
needs the VictoriaLogs datasource), so nothing else was lost. After the sync, Grafana lists 1
dashboard. To bring the bundle back, set `enabled: true` again.

**Important gotcha found during the removal:** `enabled: false` alone did NOT delete the 43
already-created ConfigMaps. The bundled dashboards are created by the chart's sync Job
(`app.kubernetes.io/managed-by: sync-job`, owner is the sync-job ServiceAccount), NOT by Helm
directly, so ArgoCD showed Synced/Healthy with all 44 ConfigMaps still present and had nothing
to prune. The 43 `victoria-metrics-vmks-dashboard-*` ConfigMaps had to be deleted manually
(`kubectl delete cm -n monitoring -l app.kubernetes.io/managed-by=sync-job`); the sidecar then
removed them from Grafana within ~40s. With `enabled: false` in git, the sync job should not
recreate them on future upgrades — but verify the dashboard count after the next stack upgrade;
if they ever come back, the same delete command is the fix.

## Honest reading notes (also in the panel descriptions)

- **Panels 1/4/5/6 are noise-cleaned since 2026-11-10.** See "What is excluded as noise" above.
  Before the clean-up panel 1 showed ~78,800 errors/day, 99% Glance + Hoarder repeats; after, ~90.
  A new error is a line you do not recognise in panel 6. The flat ~3,000/hour in panel 4 is gone
  with the noise; a spike above near-zero is what matters now.
- **Panel 2 is clean since 2026-11-10.** Before, all 168–192 warnings were VictoriaLogs itself
  (retention drops + startup send failures). After excluding the monitoring namespace it showed 2
  (ArgoCD dashboard-JSON warnings, already fixed, history only). See the exclusion section for the
  trade-off.
- **Panel 3 / 8(C):** 98 failed Gatus checks, mostly Grafana failing during the morning
  redeploy. Live up/down truth is https://gatus.npty.online, not this number.
- **Panel 8 is thin on purpose.** Only real events are shown: heartbeats (2 lines, one each
  from poke-hub and friendly-actual-budget, both manual checks, not a regular pulse),
  wallet-queue jobs (7 lines), and poke-hub completed tool calls (26 in 24h). The heartbeat target uses the action field
  (`filter action:"heartbeat"`): the exact phrase `"heartbeat completed"` also matched
  ArgoCD log lines that embed this dashboard JSON (its description mentions the phrase).
  NOT here: friendly-actual-budget receipt events (0 lines so far - see the second clean-up
  section; they will appear on the next real receipt) and the rail apps (sentence-gym,
  article-archive, manga-reader, rail-console, whoop-mcp-server are silent - 0 lines in
  7 days). Do not add a panel for an event until its lines exist in VL.
- **History:** k8s logs only go back to the morning of 2026-11-10 (fresh PVCs, no backfill);
  Docker logs go back 14 days. Counts for "last 24h" are complete for Docker, partial for k8s
  before this morning.
- **Stat/timeseries rendering:** stats queries return their count in a `count(*)` label.
  The stat and timeseries panels use the standard Grafana transformations
  "Labels to fields" + "Convert field type (count(*) to number)" to turn that label into
  a number. Each query was verified to return data through the Grafana API
  (`/api/ds/query` from inside K12) before this dashboard was pushed.

## Files

- `logs-at-a-glance.json` — the dashboard (source of truth).
- `logs-at-a-glance-configmap.yaml` — ConfigMap wrapper (generated from the JSON;
  regenerate with `build_dashboard.py`, do not hand-edit the embedded JSON).
- `<app-slug>.json` + `<app-slug>-configmap.yaml` — one per-app dashboard (generated with
  `build_per_app_dashboards.py` in `~/workspace/research_notes/k12-logging-onboarding-20261110/`).
  Generator scripts live in the research notes, not in k12-infra.
- `README.md` — this file.
- `argocd/applications/monitoring-dashboards.yaml` — ArgoCD Application (plain manifests,
  same pattern as `monitoring-scrapes`).
