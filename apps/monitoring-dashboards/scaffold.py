#!/usr/bin/env python3
"""Create a per-app dashboard <slug>.json for a k8s app, cloned from wallet-queue.json.

Usage:
  python3 scaffold.py <slug> "<Title>" <namespace> "<about markdown>" [--gatus "<Gatus endpoint name>"]
Then run build.py to generate the ConfigMap, commit both files.

With --gatus: Errors / Warnings / Failed Gatus checks stats + a live "Log lines" stat next to the About text.
Without:      Errors / Warnings / Log lines stats (no Gatus endpoint to check).
"""
import copy
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
DS = {"type": "victoriametrics-logs-datasource", "uid": "VictoriaLogs"}
GLANCE = "https://grafana.npty.online/d/logs-at-a-glance"


def stat(template, pid, title, expr, desc, x, y, w, h):
    p = copy.deepcopy(template)
    p.update(id=pid, title=title, description=desc)
    p["gridPos"] = {"x": x, "y": y, "w": w, "h": h}
    p["targets"] = [{"refId": "A", "datasource": DS, "expr": expr, "queryType": "stats"}]
    return p


def build(slug, title, ns, about, gatus=None):
    d = json.loads((HERE / "wallet-queue.json").read_text())
    text, errors, warns, gate, latest, biz = d["panels"]
    sel = '{kubernetes.pod_namespace="%s"}' % ns
    d.update(uid=f"app-{slug}", title=title)
    d["version"] = 1

    text["options"]["content"] = f"**{title}** - {about} Back to [Logs at a glance]({GLANCE})."
    text["gridPos"] = {"x": 0, "y": 0, "w": 24, "h": 4}

    panels = [text]
    panels.append(stat(errors, 2, "Errors in the last 24 hours", sel + ' | filter "Error" | stats count()',
                       f'LogsQL: {sel} | filter "Error" | stats count(). Errors from this app only, last 24h.', 0, 4, 8, 7))
    panels.append(stat(warns, 3, "Warnings in the last 24 hours", sel + ' | filter "warn" | stats count()',
                       f'LogsQL: {sel} | filter "warn" | stats count(). Warnings from this app only, last 24h.', 8, 4, 8, 7))
    if gatus:
        gexpr = '{kubernetes.pod_namespace="gatus"} | filter "endpoint=%s" | filter "success=false"' % gatus
        panels.append(stat(gate, 4, "Failed Gatus checks in the last 24 hours", gexpr + " | stats count()",
                           f"LogsQL: {gexpr} | stats count(). Failed Gatus checks of this app, last 24h. "
                           "Live status is https://gatus.npty.online - that page, not this number, is the up/down truth.",
                           16, 4, 8, 7))
        text["gridPos"]["w"] = 18
        panels.append(stat(warns, 7, "Log lines in the last 24 hours", sel + " | stats count()",
                           f"LogsQL: {sel} | stats count(). Live count of all log lines from this app. 0 means the app is quiet or silent.",
                           18, 0, 6, 4))
    else:
        panels.append(stat(warns, 4, "Log lines in the last 24 hours", sel + " | stats count()",
                           f"LogsQL: {sel} | stats count(). Live count of all log lines from this app. 0 means the app is quiet or silent.",
                           16, 4, 8, 7))

    latest["targets"] = [{"refId": "A", "datasource": DS, "expr": sel}]
    latest["description"] = f"LogsQL: {sel}. All log lines from this app, newest first. Empty means the app is silent or the namespace has no pods."
    panels.append(latest)

    biz["targets"] = [{"refId": "A", "datasource": DS, "expr": sel}]
    biz["description"] = f"{sel}, newest first. This app's own log lines are its business events."
    if gatus:
        biz["targets"].append({"refId": "B", "datasource": DS, "expr": gexpr})
        biz["description"] += f" Stream B adds failed Gatus checks for {gatus}."
    panels.append(biz)

    d["panels"] = panels
    return d


def main():
    args = sys.argv[1:]
    gatus = None
    if "--gatus" in args:
        i = args.index("--gatus")
        gatus = args[i + 1]
        del args[i:i + 2]
    if len(args) != 4:
        print(__doc__)
        return 2
    slug, title, ns, about = args
    out = HERE / f"{slug}.json"
    if out.exists():
        print(f"{out.name} exists; refusing to overwrite")
        return 1
    out.write_text(json.dumps(build(slug, title, ns, about, gatus), indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out.name}; now run build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
