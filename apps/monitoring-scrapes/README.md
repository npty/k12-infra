# Extra Prometheus scrapes for the VictoriaMetrics stack (vmagent).
# Plain-manifest ArgoCD Application `monitoring-scrapes` (see
# argocd/applications/monitoring-scrapes.yaml). vmagent has
# selectAllByDefault: true, so any VMServiceScrape / VMScrapeConfig in the
# cluster is picked up automatically; these objects live in `monitoring`
# but scrape services/pods in other namespaces.
#
# Why not ServiceMonitors: the VM operator installs only its own
# VMServiceScrape/VMScrapeConfig CRDs; there are NO monitoring.coreos.com
# CRDs in this cluster (the Gatus serviceMonitor had to be disabled for
# exactly this reason).
#
# Job names (what to query in PromQL):
#   sealed-secrets, gatus,
#   argocd-application-controller, argocd-repo-server,
#   argocd-notifications-controller, argocd-applicationset-controller,
#   argocd-server, qdrant, cadvisor-docker
#
# Deliberately NOT scraped (see logs-metrics-fixes-2026-11-10.md):
#   - argocd dex-server :5558/metrics: nothing listens (connection refused).
#   - uptime-kuma :8125/metrics: HTTP 401, basic auth with the Kuma admin
#     login (or X-API-Key once an API key exists, which permanently disables
#     basic auth). No credential is available to the scraper; Euro to create
#     a dedicated API key in the Kuma UI if he wants this scraped.
#   - Next.js apps / wallet-queue / whoop: no /metrics endpoint.
#   - rail-console :8080/metrics: 401, auth-gated.
