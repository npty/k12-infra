# K12 infrastructure — GitOps repo

This repo is the source of truth for everything running on Euro's K12
Kubernetes (k3s) cluster. ArgoCD watches this repo and makes the cluster match
it: push here = deploy.

Layout:

- `charts/web-app/` — generic Helm chart for a containerized web app
  (Deployment + ClusterIP Service). Most apps only need a values file.
- `apps/<name>/values.yaml` — per-app settings (image, tag, port, hostname, env).
- `argocd/applications/` — one ArgoCD Application manifest per app, pointing at
  `apps/<name>` with the `web-app` chart.

Flow: app repo pushes image to GHCR → ArgoCD Image Updater notices the new tag
→ ArgoCD syncs the chart → new pods roll out. Roll back by reverting the tag.
