# OTLP ingest proxy for VictoriaLogs (poke-hub PoC, 2026-11-10).
# Plain-manifest ArgoCD Application `otlp-proxy` (see
# argocd/applications/otlp-proxy.yaml).
#
# Why a proxy: vlsingle is ClusterIP-only and accepts unauthenticated
# writes. poke-hub (Vercel) must POST OTLP over the public internet, so
# it goes through this nginx, which enforces HTTP basic auth and forwards
# to VL. Public hostname: otlp.npty.online (Cloudflare tunnel route in
# the in-cluster cloudflared ConfigMap + DNS CNAME -> the 89e1de75 tunnel;
# the Oct-16 "add the route to the host k12-tipis.yml too" rule is STALE:
# the tunnels split since then -- host k12-tipis.yml is tunnel 04c03f55
# (Docker apps only) and k8s hostnames' CNAMEs all point at 89e1de75, so
# only the in-cluster ConfigMap carries k8s routes now).
#
# Path trick (verified live 2026-11-10 with a hand-built protobuf POST):
# VL accepts OTLP/HTTP protobuf ONLY at /insert/opentelemetry/v1/logs
# (JSON is rejected, /v1/logs is "unsupported path"). poke-hub's
# OTLPLogExporter posts to ${endpoint}/v1/logs, so setting
# OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.npty.online/insert/opentelemetry
# makes it post to exactly VL's path. The proxy preserves the path
# (proxy_pass with no URI part); no rewriting is needed.
#
# Auth: HTTP basic auth, user `poke-hub`. The htpasswd file lives in
# Secret `otlp-proxy-auth` (key `htpasswd`), created OUT OF BAND on K12
# (same pattern as alertmanager-config / gatus-secrets) so no credential
# is ever in git. The same credential is set in Vercel as
# HYPERDX_API_KEY="Basic <base64(user:password)>" because poke-hub sends
# its apiKey raw as the `authorization:` header. Plaintext password lives
# only in the Vercel dashboard; rotate by regenerating both sides.
# Apply order: create the Secret on K12 FIRST, then sync this app
# (the pod cannot start without the Secret).
#
# Pin: nginx:1.27.4-alpine (verified on Docker Hub 2026-11-10).
