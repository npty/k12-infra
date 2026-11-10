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
| 1 | Errors in the last 24 hours (stat) | `* \| filter "Error" \| stats count()` | ~69,700 |
| 2 | Warnings in the last 24 hours (stat) | `* \| filter "warn" \| stats count()` | 168 |
| 3 | Failed checks in the last 24 hours, Gatus (stat) | `{kubernetes.pod_namespace="gatus"} \| filter "success=false" \| stats count()` | 98 |
| 4 | Errors per hour (timeseries) | `* \| filter "Error" \| stats by (_time:1h) count()` | ~3,000/hour, flat |
| 5 | Top errors by app (table) | `* \| filter "Error" \| stats by (container, kubernetes.pod_namespace) count()` | Glance ~52,400; Hoarder ~17,200 |
| 6 | Latest error lines (logs) | `* \| filter "Error"` | — |
| 7 | Latest warnings (logs) | `* \| filter "warn"` | — |
| 8 | Business events (logs, 3 targets) | (A) `* \| filter "heartbeat"` (B) `{kubernetes.pod_namespace="wallet-queue"}` (C) `{kubernetes.pod_namespace="gatus"} \| filter "success=false"` | heartbeat 1; wallet-queue 7 |

## Honest reading notes (also in the panel descriptions)

- **Panel 1 is dominated by two repeating issues.** Glance crash-loops (~52k lines/day,
  each real line duplicated ~14x in VictoriaLogs) and Hoarder's missing Chrome
  (~17k/day, retrying every 5s). Together they are ~99% of "Error" lines. A new error
  is a line you do not recognise in panel 6. The flat ~3,000/hour in panel 4 is normal;
  a spike above it is what matters.
- **Panel 2 is almost entirely VictoriaLogs itself.** All 168 warnings at build time were
  in the `monitoring` namespace: VictoriaLogs warning that old Docker log lines are too
  old for the 14-day retention and were dropped. Not app problems.
- **Panel 3 / 8(C):** 98 failed Gatus checks, mostly Grafana failing during the morning
  redeploy. Live up/down truth is https://gatus.npty.online, not this number.
- **Panel 8 is thin on purpose.** Only real events are shown: poke-hub heartbeat (1 line,
  a manual check, not a regular pulse) and wallet-queue jobs (7 lines). NOT here:
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
