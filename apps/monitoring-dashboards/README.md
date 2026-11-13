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
(2026-11-10 ~13:10 Dubai); panel 8 and the per-panel notes carry 2026-11-13 values
from the audit below, and they change as new logs arrive.

| # | Panel | LogsQL | At build time |
|---|---|---|---|
| 1 | Errors in the last 24 hours (stat) | `* \| filter "Error" \| filter NOT container:"/glance_migrated-glance-1" \| filter NOT "hoarder-chrome" \| filter NOT "helm" \| filter NOT "inspect" \| filter NOT "ACME" \| filter NOT "skipping" \| filter NOT "could not fetch logs for container" \| stats count()` | 24 on 2026-11-13, all Immich (was 9 on 2026-11-11, ~78,800 before the first clean-up, ~183 before the second) |
| 2 | Warnings in the last 24 hours (stat) | `* \| filter "warn" \| filter NOT kubernetes.pod_namespace:"monitoring" \| stats count()` | 0 on 2026-11-13 (was 2, and 192 before the clean-up) |
| 3 | Failed checks in the last 24 hours, Gatus (stat) | `{kubernetes.pod_namespace="gatus"} \| filter "success=false" \| stats count()` | 2 on 2026-11-13 (was 98) |
| 4 | Errors per hour (timeseries) | same error query as panel 1, `\| stats by (_time:1h) count()` | at most 4 in any hour on 2026-11-11 |
| 5 | Top errors by app (table) | same error query as panel 1, `\| stats by (container, kubernetes.pod_namespace) count()` | Immich 24 on 2026-11-13 (was Immich 4; ArgoCD 2; monitoring 1; cloudflared 1; Runtipi 1 on 2026-11-11) |
| 6 | Latest error lines (logs) | same error query as panel 1, no stats | — |
| 7 | Latest warnings (logs) | `* \| filter "warn" \| filter NOT kubernetes.pod_namespace:"monitoring"` | — |
| 8 | Business events (logs, 5 targets) | (A) `* \| filter action:"heartbeat"` (B) `{kubernetes.pod_namespace="wallet-queue"}` (C) `{kubernetes.pod_namespace="gatus"} \| filter "success=false"` (D) `* \| filter service.name:poke-hub \| filter "capability.call" \| filter "completed"` (E) `* \| filter service.name:friendly-actual-budget \| filter NOT action:"heartbeat"` | heartbeats 2 in 24h; wallet-queue 4; Gatus failed 2; poke-hub tool calls 17; receipt events 4 (2 queued + 2 confirmed) — all checked 2026-11-13 ~16:50 Dubai |

## Per-app dashboards (added 2026-11-11)

One dashboard per app, same layout, same VictoriaLogs datasource, same ConfigMap
provisioning (one ConfigMap per dashboard in this directory, `grafana_dashboard: "1"`).
Each has: an "About this app" text panel (with a link back here), Errors 24h, Warnings 24h,
a health stat (failed Gatus checks for k8s apps, log-lines count for Vercel apps),
Latest log lines, and Business events for that app only. Every panel description
carries its exact LogsQL.

| App | Dashboard | Logging on 2026-11-13 (re-checked, was 2026-11-11) |
|---|---|---|
| Sentence Gym | https://grafana.npty.online/d/app-sentence-gym | Still silent, 0 lines in 7d. Running, ArgoCD Synced/Healthy, Gatus checks it every minute. |
| Rail Console | https://grafana.npty.online/d/app-rail-console | Still silent, 0 lines in 7d. Same as above. |
| Article Archive | https://grafana.npty.online/d/app-article-archive | Still silent, 0 lines in 7d. Same as above. |
| Manga Reader | https://grafana.npty.online/d/app-manga-reader | Still silent, 0 lines in 7d. Same as above. |
| Whoop MCP Server | https://grafana.npty.online/d/app-whoop-mcp-server | Still silent, 0 lines in 7d. Same as above. |
| Wallet Queue | https://grafana.npty.online/d/app-wallet-queue | 4 lines in 24h, 15 in 7d: 7 enqueued, 7 completed, 0 failed (ios-wallet-automation 5, pwa 1, smoke-test 2 in 7d). |
| Poke Hub | https://grafana.npty.online/d/app-poke-hub | 184 lines in 24h, 656 in 7d: completed tool calls 17 in 24h, 73 in 7d. Whoop calls new since 11 Nov (get_today 11, get_recovery_trends 6 in 7d). Bursty: 5 whoop.get_today calls in one minute at 12:33 UTC. |
| Friendly Actual Budget | https://grafana.npty.online/d/app-friendly-actual-budget | Receipts are flowing now: 4 lines in 24h, 9 in 7d — wallet-ingest-queued 2 + transaction-confirmed 2 in 24h (13 Nov 08:49 and 09:24 Dubai), 4 + 4 in 7d. New "Receipts queued" stat panel. |

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

## 2026-11-13 audit — what else could go on a dashboard

Full re-check of every app, live in VictoriaLogs (24h and 7d, verified through the
Grafana `/api/ds/query` path), plus ArgoCD (12 apps, all Synced/Healthy), `docker ps`
(68 running containers), and Gatus (10 endpoints). What changed since 2026-11-11:

- **Main dashboard, panel 8:** new target (E), friendly-actual-budget receipt events
  (`* | filter service.name:friendly-actual-budget | filter NOT action:"heartbeat"`).
  Real receipts landed: 2 queued + 2 confirmed in 24h, 4 + 4 in 7d.
- **Main dashboard, error panels:** exact-phrase exclusion for Alloy "could not fetch
  logs for container" (see "Third clean-up" above). Filtered errors 28 -> 24, all Immich.
- **Friendly Actual Budget dashboard:** new "Receipts queued in the last 24h" stat (2 on
  2026-11-13); About and business-panel text rewritten with the real counts.
- **Poke Hub dashboard:** About and business-panel text refreshed (184 lines/24h, 656/7d;
  completed calls 17/24h, 73/7d; Whoop calls new since 11 Nov).
- **Wallet Queue dashboard:** About text refreshed (4 lines/24h, 15/7d; 7 enqueued,
  7 completed, 0 failed).
- **The 5 silent rail dashboards:** About text re-checked, still 0 lines in 7d on
  2026-11-13; only the check date changed.
- **Main dashboard numbers now:** filtered errors 24 in 24h (all Immich), unfiltered 87,
  warnings (excl. monitoring) 0, Gatus failed 2 in 24h (Grafana 1, Article Archive 1,
  one transient blip 12 Nov 15:03), heartbeats 2 in 24h (both friendly-actual-budget,
  12:36/12:38 UTC).

### Docker apps checked and deliberately left out

| App | Lines 24h | Errors 24h | Why no dashboard |
|---|---|---|---|
| Immich (server) | 1,119 | 24 | Errors only, one known pattern (NVENC fallback, encodes still succeed); non-error lines are NestJS service chatter. Already surfaced on the main dashboard. See borderline below. |
| Hoarder | 5,903 | 0 | Almost all `/api/health` HEAD checks every 30s. 0 bookmark/link/save lines in 7d. Its old Chrome errors (66,837 in 7d) stopped with the crawler. |
| Nextcloud (app container) | ~100/day (727 in 7d) | 0 | Apache access logs only. Real file ops exist (see borderline). |
| Actual Budget | 0 | 0 | Emits nothing (silent since Oct 25). Nothing to show. |
| Tandoor | 35,072 | 0 | Wget health-check GETs of `/` and the login page. Pure noise. |
| Meilisearch | 0 | 0 | Emits nothing. |
| Wallos | 741 | 0 | `GET /health.php` every 2 min. Pure noise. |
| Vaultwarden | 0 | 0 | Emits nothing. |
| Plex | 0 | 0 | Emits nothing. |
| Runtipi | 6 | 0 | Repo-clone housekeeping only. |
| n8n | 3 | 0 | Near-silent. |
| Stirling PDF | 450 | 0 | MCP catalog refresh spam every 5 min. |
| Filebrowser / Shlink / Memos / Metube / qBittorrent / Dozzle / Beszel | 0 | 0 | Emit nothing. |
| Homebox | 5,877 | 0 | `/api/v1/status` request pairs every ~30s. Health-check noise. |
| Openship API | 34,235 | 0 | `/api/health` + auth session polling. Noise. |
| Excalidraw | 2,938 | 0 | Wget health checks every 30s. |
| Docuseal | 244 | 0 | Mostly 404s from an external scanner IP. Not a dashboard. |
| Resilio Sync | 40,260 | 0 | CoreState interface dumps. Noise. |
| Uptime Kuma | 0 (978 in 7d) | 0 | Logs only on monitor state changes. Its 7d lines are all WARNs from one transient blip on 11 Nov 21:09-21:10, when several monitors (Poke Hub, Sentence Gym, CFO, E1002 Dashboard) timed out at once. A second monitoring system; Gatus already covers this. |
| nextcloud-rag-rag-app | 125,621 | 0 | The #1 log volume on the box: uvicorn access logs + DeepSeek API call logs. Noise, not signal. Flagged here because the volume itself is worth knowing. |

Also checked: k8s `data` namespace (Postgres/Redis) logs 0 lines - not Euro-facing, skipped.
No other Vercel app Euro uses ships logs to K12: only `poke-hub` (576 lines/7d),
`friendly-actual-budget` (9/7d) and the probe service `poke-hub-probe` (4 lines, OTLP
connectivity probes, not an app) appear as `service.name` values. fire-tracker,
card-picker and multisend have no OTel logging into VictoriaLogs - they would need
instrumentation first (see below).

### Borderline candidates (Euro to pick)

- **Nextcloud** - the app container's access log shows real file operations, ~100 lines/day:
  the nightly Actual Budget backup zips landing via WebDAV (PUT `actual-budget-thb-....zip`
  201, DELETE of old ones, e.g. 12 Nov 23:00). A dashboard would be Errors (0) + "Latest
  file operations". Against: it mostly duplicates the poke-hub `backup_to_nextcloud` tool
  calls (6 in 7d), which are already on the poke-hub dashboard and the main panel 8.
- **Immich** - the server container logs "Successfully encoded <uuid>" lines (12 lines with
  "encoded" in 24h) alongside the 24 NVENC fallback errors. A dashboard could show Errors
  24h + videos encoded. Against: the success signal is thin, and phrase filters on
  Immich's ANSI-coloured NestJS logs are unreliable (`filter "Successfully"` returns 0
  even though the words are visible in the line - tokenisation splits on the colour codes).

### Needs a code change first (not dashboard work)

- **Receipt lines have no amount or merchant.** friendly-actual-budget logs
  `transaction-confirmed completed` / `wallet-ingest-queued completed` with no amount,
  payee, or source. Showing "AED X at Y" on a dashboard needs the log line enriched in
  `apps/api/src/app.ts`. A separate agent is adding logs across the apps; this is one to
  feed it.
- **Silent rail apps** (sentence-gym, rail-console, article-archive, manga-reader,
  whoop-mcp-server): still 0 lines on 2026-11-13. Their dashboards already query the
  right namespaces, so new log lines will appear automatically once the logging work
  lands - only the About text will need a refresh. Specific events to watch for:
  manga-reader weekly fetch cron (Mondays 09:00 Dubai, next run 16 Nov - no fetch lines
  yet), whoop-mcp-server token refresh/recovery (no `token`/`refresh` lines in 7d),
  article-archive adds (no `article` lines in 7d).
- **Vercel apps without OTel** (fire-tracker, card-picker, multisend): no logs reach
  VictoriaLogs at all. A dashboard for any of them needs OTel shipping added first, the
  way poke-hub and friendly-actual-budget have it.
- **Immich NVENC errors** are a host/GPU permission issue, not a dashboard problem:
  the container cannot init the CUDA device (`Operation not permitted`), falls back to
  software encode, and succeeds. Fixing it means giving the container GPU access or
  disabling NVENC; the dashboard can only keep showing the ~24/day.

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

  **Update 2026-11-13:** the receipts have now landed for real - 2 queued + 2 confirmed in
  the last 24h (13 Nov 08:49 and 09:24 Dubai), 4 + 4 in 7d - so target (E) was added to the
  main dashboard's business panel and a "Receipts queued in the last 24h" stat was added to
  the friendly-actual-budget dashboard (see "2026-11-13 audit" below). The paragraph above
  is kept as history: on 2026-11-11 the count really was 0.

## Third clean-up (2026-11-13) — one more Alloy wording

The filtered error count on 2026-11-13 was 28 in 24h (was 9 on 2026-11-11): Immich 24,
monitoring 4. The 4 monitoring lines are Alloy `could not fetch logs for container`
errors - the same dead-container tailing cause as the already-excluded "could not inspect
container info" lines, just the other wording (one line every ~3h per dead container id).
Scope checked through the Grafana API: the exact phrase `could not fetch logs for container`
appears in 4 lines in 24h, all in the monitoring namespace, 0 outside it (5 in 7d). A
single-word filter on "fetch" was NOT used: "fetch" appears in 62 lines/24h, including 4
outside monitoring (ArgoCD helm-template lines, already excluded by "helm") - too broad.
The exact phrase is now excluded from the error panels (panels 1, 4, 5, 6), taking the
filtered count 28 -> 24, all Immich. The Immich 24 are the known NVENC "Operation not
permitted" fallback: ffmpeg cannot init the GPU device, retries with NVENC disabled, and
the encode then succeeds - videos are not lost, but the error repeats once per video,
~24/day, up from 4 on 2026-11-10. No new exclusion was made for anything else.

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
- **Panel 8 is thin on purpose.** Only real events are shown: heartbeats (2 in the last 24h
  at verification on 2026-11-13, both friendly-actual-budget manual checks at 12:36/12:38 UTC,
  not a regular pulse),
  wallet-queue jobs (4 lines in 24h), failed Gatus checks (2), poke-hub completed tool calls
  (17 in 24h, 73 in 7d), and friendly-actual-budget receipt events (target E, added
  2026-11-13: 2 queued + 2 confirmed in 24h - real receipts, the first since the OTel deploy).
  The heartbeat target uses the action field (`filter action:"heartbeat"`): the exact phrase
  `"heartbeat completed"` also matched ArgoCD log lines that embed this dashboard JSON (its
  description mentions the phrase). The rail apps (sentence-gym, article-archive, manga-reader,
  rail-console, whoop-mcp-server) are still silent - 0 lines in 7 days, re-checked 2026-11-13.
  Do not add a panel for an event until its lines exist in VL.
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
