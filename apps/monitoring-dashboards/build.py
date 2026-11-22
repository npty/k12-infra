#!/usr/bin/env python3
"""Regenerate <name>-configmap.yaml from <name>.json (the JSON is the source of truth).

Usage: python3 apps/monitoring-dashboards/build.py [--check]
  --check  exit 1 if any ConfigMap is out of date (no writes)
ArgoCD syncs only the *-configmap.yaml files (*.json is excluded), so run this
after every JSON edit and commit both files.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent

TEMPLATE = """apiVersion: v1
kind: ConfigMap
metadata:
  name: {name}-dashboard
  namespace: monitoring
  labels:
    app.kubernetes.io/instance: victoria-metrics
    app.kubernetes.io/name: grafana
    grafana_dashboard: "1"
data:
  {name}.json: |
{body}
"""


def render(path: pathlib.Path) -> str:
    name = path.stem
    d = json.loads(path.read_text())
    body = "\n".join("    " + line for line in json.dumps(d, indent=2, ensure_ascii=False).splitlines())
    return TEMPLATE.format(name=name, body=body)


# apps/<dir> entries that are platform plumbing, not workloads that need a per-app dashboard.
NOT_DASHBOARDS = {"apps.json"}  # generator input, not a dashboard
INFRA_APPS = {"alloy", "gatus", "monitoring-dashboards", "monitoring-scrapes", "otlp-proxy", "victoria-metrics"}


def missing_dashboards() -> list[str]:
    apps = HERE.parent
    return sorted(
        p.name for p in apps.iterdir()
        if p.is_dir() and p.name not in INFRA_APPS and not (HERE / f"{p.name}.json").exists()
    )


def main() -> int:
    check = "--check" in sys.argv
    missing = missing_dashboards()
    for m in missing:
        print(f"missing dashboard: apps/{m} has no apps/monitoring-dashboards/{m}.json (see scaffold.py)")
    stale = []
    for j in sorted(x for x in HERE.glob("*.json") if x.name not in NOT_DASHBOARDS):
        out = HERE / f"{j.stem}-configmap.yaml"
        new = render(j)
        if not out.exists() or out.read_text() != new:
            stale.append(out.name)
            if not check:
                out.write_text(new)
    for s in stale:
        print(("stale: " if check else "wrote: ") + s)
    return 1 if (check and (stale or missing)) else 0


if __name__ == "__main__":
    sys.exit(main())
