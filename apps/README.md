# Per-app wrappers live here: apps/<name>/
#
# Each app is a thin Helm chart with a file:// dependency on the shared
# ../../charts/web-app chart. Files per app:
#
#   apps/<name>/Chart.yaml   - declares the dependency (see example below)
#   apps/<name>/values.yaml  - all settings nested under the `web-app:` key
#
# Example Chart.yaml:
#   apiVersion: v2
#   name: word-explorer
#   type: application
#   version: 0.1.0
#   dependencies:
#     - name: web-app
#       version: 0.1.0
#       repository: file://../../charts/web-app
#
# Example values.yaml:
#   web-app:
#     replicaCount: 1
#     image:
#       repository: ghcr.io/npty/word-explorer
#       tag: latest
#     containerPort: 3000
#     host: word-explorer-k12.npty.online
