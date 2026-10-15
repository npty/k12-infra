# One ArgoCD Application manifest per app.
# Each points at its wrapper chart in ../apps/<name>:
#
# apiVersion: argoproj.io/v1alpha1
# kind: Application
# metadata:
#   name: word-explorer
#   namespace: argocd
# spec:
#   project: default
#   source:
#     repoURL: https://github.com/npty/k12-infra.git
#     targetRevision: HEAD
#     path: apps/word-explorer
#   destination:
#     server: https://kubernetes.default.svc
#     namespace: word-explorer
#   syncPolicy:
#     automated: {prune: true, selfHeal: true}
#     syncOptions: [CreateNamespace=true]
