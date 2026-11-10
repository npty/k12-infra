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
#
# ENCODING (2026-11-10, the blocker that killed the first heartbeat):
# VL rejects OTLP/JSON ("json encoding isn't supported for opentelemetry
# format. Use protobuf encoding") and poke-hub's
# @opentelemetry/exporter-logs-otlp-http@0.218.0 HARD-CODES
# JsonLogsSerializer (verified from the published package source) -- no
# env var switches it to protobuf (OTEL_EXPORTER_OTLP_LOGS_PROTOCOL is
# ignored by this package; the var was set in Vercel, tested, and
# removed). So nginx routes /insert/opentelemetry/v1/logs to the
# `translator` sidecar (python:3.12-slim, otlp-translate.py from
# ConfigMap otlp-translator, stdlib only, no pip, no custom image),
# which re-encodes the exporter's JSON as protobuf and forwards it to
# VL. The translator was unit-tested byte-identical against the
# opentelemetry-proto reference library (AnyValue string_value=1,
# bool_value=2, int_value=3, double_value=4, array_value=5,
# kvlist_value=6, bytes_value=7; LogRecord.flags is fixed32).
# /v1/traces and /v1/metrics still go to VL direct and 400 there
# (no VictoriaTraces; VM metrics ingest is a different path) -- the
# SDK fails open on those and they do not affect the audit-log sink.
