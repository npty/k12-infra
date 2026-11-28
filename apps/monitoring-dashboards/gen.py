#!/usr/bin/env python3
"""Generate the K12 Overview and every per-app dashboard JSON from apps.json.

Usage: python3 gen.py        (then python3 build.py to make the ConfigMaps)

logs-at-a-glance.json is hand-maintained (not generated). Everything else listed in
apps.json, plus k12-overview.json, is overwritten by this script: edit apps.json or
this file, never the generated JSON.
"""
import copy
import json
import pathlib
import sys

import metrics

HERE = pathlib.Path(__file__).parent
VL = {"type": "victoriametrics-logs-datasource", "uid": "VictoriaLogs"}
VM = {"type": "prometheus", "uid": "VictoriaMetrics"}
OVERVIEW = "/d/k12-overview"
STATUS_PAGE = "https://gatus.npty.online"

GREEN, YELLOW, ORANGE, RED, BLUE = "green", "yellow", "orange", "red", "blue"
LOG_OPTS = {"showTime": True, "showLabels": False, "showCommonLabels": False, "wrapLogMessage": True,
            "sortOrder": "Descending", "dedupStrategy": "none", "enableLogDetails": True, "prettifyLogMessage": False}
UP_DOWN = [{"type": "value", "options": {"1": {"text": "UP", "color": GREEN, "index": 0},
                                           "0": {"text": "DOWN", "color": RED, "index": 1}}}]


class Ids:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return self.n


def steps(*pairs):
    return [{"color": c, "value": v} for c, v in pairs]


def lq(expr, ref="A", qtype=None, step=None):
    t = {"refId": ref, "datasource": VL, "expr": expr}
    if qtype:
        t["queryType"] = qtype
    if step:
        t["step"] = step
    return t


def pq(expr, ref="A", legend="__auto", instant=False):
    return {"refId": ref, "datasource": VM, "expr": expr, "legendFormat": legend,
            "instant": instant, "range": not instant}


def stat(ids, title, targets, x, y, w, h, thr, unit="short", mappings=None, no_value="0",
         desc="", decimals=None, text_mode="auto", color_mode="background", links=None):
    d = {"color": {"mode": "thresholds"}, "unit": unit, "noValue": no_value,
         "thresholds": {"mode": "absolute", "steps": thr}, "mappings": mappings or []}
    if decimals is not None:
        d["decimals"] = decimals
    return {"id": ids(), "type": "stat", "title": title, "description": desc,
            "datasource": targets[0]["datasource"], "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": targets,
            "fieldConfig": {"defaults": d, "overrides": []},
            "options": {"reduceOptions": {"values": False, "calcs": ["lastNotNull"], "fields": ""},
                        "orientation": "auto", "textMode": text_mode, "colorMode": color_mode,
                        "graphMode": "none", "justifyMode": "center", "wideLayout": True}}


def timeseries(ids, title, targets, x, y, w, h, unit="short", desc="", overrides=None, stack=False, ds=None, min0=True):
    custom = {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 18, "showPoints": "never", "spanNulls": True,
              "stacking": {"mode": "normal" if stack else "none", "group": "A"}}
    d = {"color": {"mode": "palette-classic"}, "unit": unit, "custom": custom, "noValue": "0"}
    if min0:
        d["min"] = 0
    return {"id": ids(), "type": "timeseries", "title": title, "description": desc,
            "datasource": ds or targets[0]["datasource"], "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": targets, "fieldConfig": {"defaults": d, "overrides": overrides or []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def logs(ids, title, targets, x, y, w, h, desc=""):
    return {"id": ids(), "type": "logs", "title": title, "description": desc, "datasource": VL,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets, "options": LOG_OPTS}


def text(ids, content, x, y, w, h, title=""):
    return {"id": ids(), "type": "text", "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "options": {"mode": "markdown", "content": content}, "transparent": not title}


def row(ids, title, y):
    return {"id": ids(), "type": "row", "title": title, "collapsed": False, "panels": [],
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}}


def ref_override(ref, name, color):
    return {"matcher": {"id": "byFrameRefID", "options": ref},
            "properties": [{"id": "displayName", "value": name},
                           {"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]}


def shell(uid, title, tags, panels, refresh="1m"):
    return {"id": None, "uid": uid, "title": title, "tags": tags, "timezone": "browser", "editable": False,
            "schemaVersion": 39, "version": 1, "fiscalYearStartMonth": 0, "graphTooltip": 1, "liveNow": False,
            "refresh": refresh, "time": {"from": "now-24h", "to": "now"},
            "timepicker": {"refresh_intervals": ["30s", "1m", "5m", "15m"]},
            "annotations": {"list": []}, "templating": {"list": []},
            "links": [{"type": "dashboards", "title": "K12 dashboards", "tags": ["k12"], "asDropdown": True,
                       "includeVars": False, "keepTime": True, "icon": "external link"},
                      {"type": "link", "title": "Status page", "url": STATUS_PAGE, "targetBlank": True,
                       "icon": "external link", "asDropdown": False, "includeVars": False, "keepTime": False,
                       "tags": []}],
            "panels": panels}


def notes_row(ids, y, notes):
    row_id = ids()
    inner = text(ids, notes, 0, y + 1, 24, 4)
    return {"id": row_id, "type": "row", "title": "Notes", "collapsed": True,
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": [inner]}


def app_dashboard(a):
    ids = Ids()
    k8s = a["kind"] == "k8s"
    if k8s:
        sel = '{kubernetes.pod_namespace="%s"}' % a["ns"]
        # "err" / "warn" in apps.json: for apps whose JSON lines carry a level.
        err, warn = a.get("err", 'filter "Error"'), a.get("warn", 'filter "warn"')
        lvl = ""
    else:
        sel = "* | filter service.name:%s" % a["service"]
        err, warn = 'filter severity_text:"error"', 'filter severity_text:"warn"'
        lvl = " | copy severity_text as level"
    ns = a.get("ns")
    gatus = a.get("gatus")

    links = [f"[{a['host']}](https://{a['host']})"] if a.get("host") else []
    head = f"**{a['title']}** · {a['tagline']}" + ("".join(" · " + l for l in links)) + f" · [Overview]({OVERVIEW})"
    panels = [text(ids, head, 0, 0, 24, 2)]

    y = 2
    err_stat = lambda w, x: stat(ids, "Errors", [lq(f"{sel} | {err} | stats count()", qtype="stats")], x, y, w, 4,
                                  steps((GREEN, None), (ORANGE, 1), (RED, 10)),
                                  desc=f"LogsQL: {sel} | {err} | stats count(). Over the selected time range.")
    warn_stat = lambda w, x: stat(ids, "Warnings", [lq(f"{sel} | {warn} | stats count()", qtype="stats")], x, y, w, 4,
                                   steps((GREEN, None), (YELLOW, 1), (ORANGE, 25)),
                                   desc=f"LogsQL: {sel} | {warn} | stats count(). Over the selected time range.")
    if k8s:
        tiles = []
        if gatus:
            tiles.append(stat(ids, "Status", [pq(f'max(gatus_results_endpoint_success{{name="{gatus}"}})', instant=True)],
                              0, y, 4, 4, steps((RED, None), (GREEN, 1)), mappings=UP_DOWN, no_value="n/a",
                              desc=f"Latest Gatus check for {gatus}. Full history: {STATUS_PAGE}"))
            tiles.append(stat(ids, "Uptime", [pq(f'avg_over_time(gatus_results_endpoint_success{{name="{gatus}"}}[$__range]) * 100', instant=True)],
                              4, y, 4, 4, steps((RED, None), (ORANGE, 95), (GREEN, 99.5)), unit="percent", decimals=2,
                              no_value="n/a", desc="Share of Gatus checks that passed in the selected time range."))
            xs = [8, 12, 16, 20]
        else:
            xs = [0, 6, 12, 18]
        w = 4 if gatus else 6
        tiles.append(stat(ids, "Pods ready", [pq(f'sum(kube_pod_status_ready{{namespace="{ns}",condition="true"}}) or vector(0)', instant=True)],
                          xs[0], y, w, 4, steps((RED, None), (GREEN, 1)),
                          desc=f"Ready pods in namespace {ns}. 0 means nothing is running."))
        tiles.append(stat(ids, "Restarts", [pq(f'sum(increase(kube_pod_container_status_restarts_total{{namespace="{ns}"}}[$__range])) or vector(0)', instant=True)],
                          xs[1], y, w, 4, steps((GREEN, None), (ORANGE, 1), (RED, 3)), decimals=0,
                          desc="Container restarts in the selected time range."))
        tiles.append(err_stat(w, xs[2]))
        tiles.append(warn_stat(w, xs[3]))
        panels += tiles
    else:
        panels.append(err_stat(8, 0))
        panels.append(warn_stat(8, 8))
        panels.append(stat(ids, "Log lines", [lq(f"{sel} | stats count()", qtype="stats")], 16, y, 8, 4,
                           steps((BLUE, None)), desc=f"LogsQL: {sel} | stats count(). 0 means the app is quiet or silent."))
    y += 4

    builder = metrics.BUILDERS.get(a["slug"])  # app-specific "what it does" panels, see metrics.py
    if builder:
        extra, y = builder(sys.modules[__name__], ids, y)
        panels += extra
        # Closes the last app section, so collapsing it leaves the panels below in view.
        panels.append(row(ids, "Logs and resources" if k8s else "Logs", y))
        y += 1

    vol_targets = [lq(f"{sel} | stats count()", "A", "statsRange", "1h"),
                   lq(f"{sel} | {err} | stats count()", "B", "statsRange", "1h")]
    vol_over = [ref_override("A", "Log lines", BLUE), ref_override("B", "Errors", RED)]
    if k8s:
        panels.append(timeseries(ids, "Log lines and errors per hour", vol_targets, 0, y, 12, 7, overrides=vol_over,
                                 desc="Hourly log volume (blue) and error lines (red)."))
        cpu = pq(f'sum(rate(container_cpu_usage_seconds_total{{namespace="{ns}",container!=""}}[5m]))', "A", "CPU (cores)")
        mem = pq(f'sum(container_memory_working_set_bytes{{namespace="{ns}",container!=""}})', "B", "Memory")
        res_over = [{"matcher": {"id": "byName", "options": "Memory"},
                     "properties": [{"id": "unit", "value": "bytes"}, {"id": "custom.axisPlacement", "value": "right"}]},
                    {"matcher": {"id": "byName", "options": "CPU (cores)"},
                     "properties": [{"id": "unit", "value": "none"}, {"id": "decimals", "value": 3}]}]
        panels.append(timeseries(ids, "CPU and memory", [cpu, mem], 12, y, 12, 7, overrides=res_over, ds=VM,
                                 desc=f"CPU (cores, left) and working-set memory (right) of namespace {ns}."))
    else:
        panels.append(timeseries(ids, "Log lines and errors per hour", vol_targets, 0, y, 24, 7, overrides=vol_over,
                                 desc="Hourly log volume (blue) and error lines (red)."))
    y += 7

    if k8s:  # plain-text lines carry no level; the panel's own filter tells us what they are
        attn = [lq(f'{sel} | {err} | format "error" as level', "A"), lq(f'{sel} | {warn} | format "warn" as level', "B")]
    else:    # OTLP lines already have severity_text
        attn = [lq(f"{sel} | {err}{lvl}", "A"), lq(f"{sel} | {warn}{lvl}", "B")]
    panels.append(logs(ids, "Needs attention: errors and warnings", attn, 0, y, 24, 7,
                       desc="Error lines (A) and warning lines (B), newest first. Empty is good."))
    y += 7
    if k8s:
        panels.append(logs(ids, "Latest log lines", [lq(sel)], 0, y, 24, 9,
                           desc=f"LogsQL: {sel}. Every line from this app, newest first."))
        y += 9
    else:
        panels.append(logs(ids, "Latest log lines", [lq(sel + lvl)], 0, y, 12, 9, desc=f"LogsQL: {sel}. Every line, newest first."))
        biz = [lq(q + lvl, chr(65 + i)) for i, q in enumerate(a.get("business", [sel]))]
        panels.append(logs(ids, "Business events", biz, 12, y, 12, 9, desc="Completed calls and heartbeats only, newest first."))
        y += 9
    panels.append(notes_row(ids, y, a["notes"]))
    tags = ["k12", "per-app", "logs"]
    return shell(f"app-{a['slug']}", a["title"], tags, panels)


def overview(apps):
    ids = Ids()
    glance = json.loads((HERE / "logs-at-a-glance.json").read_text())
    g = {p["id"]: p for p in glance["panels"]}
    noise_err = g[1]["targets"][0]["expr"]  # noise-filtered error count
    panels = [text(ids, f"**K12** · everything on one screen · [Status page]({STATUS_PAGE}) · "
                        "[Logs at a glance](/d/logs-at-a-glance) · pick an app from **K12 dashboards** (top right)", 0, 0, 24, 2)]
    y = 2
    tiles = [
        ("Down now", [pq("count(gatus_results_endpoint_success == 0) or vector(0)", instant=True)], steps((GREEN, None), (RED, 1)),
         "short", "Gatus endpoints failing right now."),
        ("Pods failing", [pq('count(kube_pod_status_phase{phase=~"Pending|Failed|Unknown"} == 1) or vector(0)', instant=True)],
         steps((GREEN, None), (ORANGE, 1)), "short", "Pods stuck Pending, Failed or Unknown."),
        ("Restarts", [pq("sum(increase(kube_pod_container_status_restarts_total[$__range])) or vector(0)", instant=True)],
         steps((GREEN, None), (ORANGE, 1), (RED, 5)), "short", "Container restarts in the selected range."),
        ("Errors", [lq(noise_err, qtype="stats")], steps((GREEN, None), (ORANGE, 1), (RED, 100)), "short",
         "Error lines across all apps (known noise excluded), selected range."),
        ("CPU", [pq('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))', instant=True)],
         steps((GREEN, None), (ORANGE, 70), (RED, 90)), "percent", "K12 node CPU."),
        ("Memory", [pq("100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)", instant=True)],
         steps((GREEN, None), (ORANGE, 75), (RED, 90)), "percent", "K12 node memory in use."),
        ("Disk /", [pq('100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})', instant=True)],
         steps((GREEN, None), (ORANGE, 75), (RED, 90)), "percent", "K12 root filesystem used."),
        ("Cert expiry", [pq("min(gatus_results_certificate_expiration_seconds) / 86400", instant=True)],
         steps((RED, None), (ORANGE, 7), (GREEN, 14)), "d", "Days until the soonest TLS certificate expires."),
    ]
    for i, (title, tg, thr, unit, desc) in enumerate(tiles):  # 4 x 2 grid: titles stay readable on narrow screens
        panels.append(stat(ids, title, tg, (i % 4) * 6, y + (i // 4) * 3, 6, 3, thr, unit=unit, desc=desc,
                           decimals=0 if unit in ("short", "d") else 1))
    y += 6

    apps_with_gatus = {a["gatus"]: a["slug"] for a in apps if a.get("gatus")}
    tile = stat(ids, "Endpoints", [pq("gatus_results_endpoint_success", legend="{{name}}", instant=True)], 0, y, 24, 5,
                steps((RED, None), (GREEN, 1)), mappings=UP_DOWN, no_value="n/a", text_mode="value_and_name",
                desc="One tile per Gatus endpoint, latest check. Click an app tile to open its dashboard.")
    tile["fieldConfig"]["overrides"] = [
        {"matcher": {"id": "byName", "options": name},
         "properties": [{"id": "links", "value": [{"title": f"{name} dashboard", "url": f"/d/app-{slug}", "targetBlank": False}]}]}
        for name, slug in sorted(apps_with_gatus.items())]
    panels.append(tile)
    y += 5

    panels.append(timeseries(ids, "Errors per hour", [lq(noise_err, "A", "statsRange", "1h")], 0, y, 12, 8,
                             overrides=[ref_override("A", "Errors", RED)], desc="Hourly error lines across all apps (known noise excluded)."))
    tbl = copy.deepcopy(g[5])
    tbl["id"] = ids()
    tbl["gridPos"] = {"x": 12, "y": y, "w": 12, "h": 8}
    panels.append(tbl)
    y += 8

    panels.append(timeseries(ids, "CPU by namespace",
                             [pq('sum by (namespace) (rate(container_cpu_usage_seconds_total{container!="",namespace!=""}[5m]))', legend="{{namespace}}")],
                             0, y, 12, 8, unit="none", stack=True, ds=VM, desc="CPU cores used per namespace (stacked)."))
    panels.append(timeseries(ids, "Memory by namespace",
                             [pq('sum by (namespace) (container_memory_working_set_bytes{container!="",namespace!=""})', legend="{{namespace}}")],
                             12, y, 12, 8, unit="bytes", stack=True, ds=VM, desc="Working-set memory per namespace (stacked)."))
    y += 8

    dash = {"id": ids(), "type": "dashlist", "title": "All dashboards", "gridPos": {"x": 0, "y": y, "w": 8, "h": 10},
            "options": {"showStarred": False, "showRecentlyViewed": False, "showSearch": True, "showHeadings": False,
                        "maxItems": 30, "query": "", "tags": ["k12"], "includeVars": False, "keepTime": True}}
    panels.append(dash)
    err_lines = copy.deepcopy(g[6])
    err_lines["id"] = ids()
    err_lines["gridPos"] = {"x": 8, "y": y, "w": 16, "h": 10}
    panels.append(err_lines)
    return shell("k12-overview", "K12 Overview", ["k12", "overview"], panels)


def write(name, d):
    (HERE / f"{name}.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print("wrote", name + ".json")


def main():
    apps = json.loads((HERE / "apps.json").read_text())
    for a in apps:
        write(a["slug"], app_dashboard(a))
    write("k12-overview", overview(apps))


if __name__ == "__main__":
    main()
