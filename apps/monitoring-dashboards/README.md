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
| 1 | Errors in the last 24 hours (stat) | `* \| filter "Error" \| filter NOT container:"/glance_migrated-glance-1" \| filter NOT "hoarder-chrome" \| stats count()` | ~91 (was ~78,800 before the 2026-11-10 noise clean-up) |
| 2 | Warnings in the last 24 hours (stat) | `* \| filter "warn" \| filter NOT kubernetes.pod_namespace:"monitoring" \| stats count()` | 2 (was 192 before the clean-up) |
| 3 | Failed checks in the last 24 hours, Gatus (stat) | `{kubernetes.pod_namespace="gatus"} \| filter "success=false" \| stats count()` | 98 |
| 4 | Errors per hour (timeseries) | `* \| filter "Error" \| filter NOT container:"/glance_migrated-glance-1" \| filter NOT "hoarder-chrome" \| stats by (_time:1h) count()` | near zero most hours |
| 5 | Top errors by app (table) | `* \| filter "Error" \| filter NOT container:"/glance_migrated-glance-1" \| filter NOT "hoarder-chrome" \| stats by (container, kubernetes.pod_namespace) count()` | ArgoCD 50; monitoring 40; cloudflared 1 |
| 6 | Latest error lines (logs) | `* \| filter "Error" \| filter NOT container:"/glance_migrated-glance-1" \| filter NOT "hoarder-chrome"` | — |
| 7 | Latest warnings (logs) | `* \| filter "warn" \| filter NOT kubernetes.pod_namespace:"monitoring"` | — |
| 8 | Business events (logs, 3 targets) | (A) `* \| filter "heartbeat completed"` (B) `{kubernetes.pod_namespace="wallet-queue"}` (C) `{kubernetes.pod_namespace="gatus"} \| filter "success=false"` | heartbeat 1; wallet-queue 7 |

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
- **Panel 8 is thin on purpose.** Only real events are shown: poke-hub heartbeat (1 line,
  a manual check, not a regular pulse) and wallet-queue jobs (7 lines). The heartbeat
  target uses the exact phrase `"heartbeat completed"`: the looser word `"heartbeat"`
  also matches ArgoCD log lines that embed this dashboard's own JSON (the panel
  description mentions the word heartbeat). NOT here:
  voice-budget receipts (friendly-actual-budget still logs only to Vercel) and the rail
  apps (sentence-gym, article-archive, manga-reader, rail-console, whoop-mcp-server are
  silent — startup logs only). Do not add a panel for an event until its lines exist in VL.
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
- `README.md` — this file.
- `argocd/applications/monitoring-dashboards.yaml` — ArgoCD Application (plain manifests,
  same pattern as `monitoring-scrapes`).
