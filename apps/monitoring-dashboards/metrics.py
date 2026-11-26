"""App-specific metric panels ("what the app does"), inserted by gen.py between the status strip and the trends.

Each builder takes the gen module `H` (panel helpers), a panel-id counter and the y to start at, and returns
(panels, next_y). Everything is derived from logs already in VictoriaLogs, so there is no extra scrape config.

Log contracts the dashboards depend on:
  poke-hub               action:capability.call  toolName, status (completed|failed), durationMs   (already shipped)
  friendly-actual-budget action:<operation>      status, durationMs; action:http-request method, path, httpStatus
  sentence-gym           event:user.action       action, outcome (ok|failed), duration_ms         (needs app change)
                         event:api.request       route, method, status, duration_ms               (already shipped)
  vegapunk               event:query.completed   channel, outcome (ok|not_found|failed), duration_ms (needs app change)
"""

BIG = {"valueSize": 44, "titleSize": 14}
HUGE = {"valueSize": 96, "titleSize": 16}


def _hero(H, ids, title, expr, x, y, w, h, thr, unit="short", desc="", text=BIG, decimals=None, no_value="0"):
    p = H.stat(ids, title, [H.lq(expr, qtype="stats")], x, y, w, h, thr, unit=unit, desc=desc, decimals=decimals,
               no_value=no_value, color_mode="value")
    p["options"]["text"] = dict(text)
    return p


def _table(H, ids, title, expr, x, y, w, h, first, cols, desc="", no_value="No data yet"):
    """Leaderboard table. `first` = (field, header) of the label column, `cols` = [(field, header, kind, thr)].

    kind: "bar" (gauge cell, scaled to the column max), "ms" (latency, coloured by thr), "n" (plain number).
    """
    overrides = [{"matcher": {"id": "byName", "options": first[0]},
                  "properties": [{"id": "displayName", "value": first[1]}, {"id": "custom.width", "value": 230}]}]
    for field, header, kind, thr in cols:
        props = [{"id": "displayName", "value": header}, {"id": "decimals", "value": 0}]
        if kind == "bar":
            props += [{"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "gradient", "valueDisplayMode": "text"}},
                      {"id": "color", "value": {"mode": "fixed", "fixedColor": "blue"}},
                      {"id": "custom.width", "value": 170}]
        elif kind == "ms":
            props += [{"id": "unit", "value": "ms"},
                      {"id": "custom.cellOptions", "value": {"type": "color-text"}},
                      {"id": "color", "value": {"mode": "thresholds"}},
                      {"id": "thresholds", "value": {"mode": "absolute", "steps": thr}}]
        elif kind == "fail":
            props += [{"id": "custom.cellOptions", "value": {"type": "color-text"}},
                      {"id": "color", "value": {"mode": "thresholds"}},
                      {"id": "thresholds", "value": {"mode": "absolute", "steps": H.steps((H.GREEN, None), (H.RED, 1))}}]
        overrides.append({"matcher": {"id": "byName", "options": field}, "properties": props})
    order = {field: i + 1 for i, (field, *_rest) in enumerate([first] + cols)}
    return {"id": ids(), "type": "table", "title": title, "description": desc, "datasource": H.VL,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [H.lq(expr, qtype="stats")],
            "transformations": [{"id": "organize", "options": {
                "excludeByName": {"Time": True}, "indexByName": order, "renameByName": {}}}],
            "fieldConfig": {"defaults": {"noValue": no_value, "custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                            "overrides": overrides},
            "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}}


def _lat_thr(H, warn, bad):
    return H.steps((H.GREEN, None), (H.ORANGE, warn), (H.RED, bad))


def _section(H, ids, y, title):
    return H.text(ids, f"### {title}", 0, y, 24, 1)


# -- Poke Hub ---------------------------------------------------------------------------------------------------

def poke_hub(H, ids, y):
    base = "service.name:poke-hub action:capability.call status:in(completed,failed)"
    ok = "service.name:poke-hub action:capability.call status:completed"
    lat = _lat_thr(H, 2000, 6000)
    P = [_section(H, ids, y, "Tool usage")]
    y += 1
    P.append(_hero(H, ids, "Tool calls", f"{base} | stats count() calls", 0, y, 6, 5, H.steps((H.BLUE, None)),
                   desc="Completed and failed MCP tool calls in the selected range."))
    P.append(_hero(H, ids, "Success rate",
                   f"{base} | stats count() if (status:completed) ok, count() total | math ok*100/total as rate | fields rate",
                   6, y, 6, 5, H.steps((H.RED, None), (H.ORANGE, 90), (H.GREEN, 98)), unit="percent", decimals=1,
                   desc="Share of tool calls that completed.", no_value="n/a"))
    P.append(_hero(H, ids, "Median latency", f"{ok} | stats quantile(0.5, durationMs) p50", 12, y, 6, 5, lat, unit="ms",
                   desc="Half of tool calls finish faster than this.", no_value="n/a"))
    P.append(_hero(H, ids, "Slow calls (p95)", f"{ok} | stats quantile(0.95, durationMs) p95", 18, y, 6, 5, lat, unit="ms",
                   desc="95% of tool calls finish faster than this.", no_value="n/a"))
    y += 5

    P.append(_table(
        H, ids, "Tool leaderboard",
        f"{base} | stats by (toolName) count() calls, count() if (status:failed) failed, quantile(0.5, durationMs) p50, "
        f"quantile(0.95, durationMs) p95, max(durationMs) max | sort by (calls desc) | limit 30",
        0, y, 14, 10, ("toolName", "Tool"),
        [("calls", "Calls", "bar", None), ("failed", "Failed", "fail", None), ("p50", "Median", "ms", lat),
         ("p95", "p95", "ms", lat), ("max", "Max", "ms", lat)],
        desc="Every tool, most used first. Latency is the time the hub spent on the call (durationMs)."))
    P.append(H.timeseries(
        ids, "Calls per hour by integration",
        [H.lq(f'{base} | extract "<integration>.<_>" from toolName | stats by (integration) count() calls',
              "A", "statsRange", "1h")], 14, y, 10, 10, stack=True,
        desc="Tool calls grouped by the part of the tool name before the dot (gmail, nextcloud, homebox...)."))
    y += 10

    P.append(H.timeseries(
        ids, "Latency per hour",
        [H.lq(f"{ok} | stats quantile(0.5, durationMs) p50, quantile(0.95, durationMs) p95", "A", "statsRange", "1h")],
        0, y, 12, 8, unit="ms", desc="Median and p95 tool latency, hourly."))
    P.append(_table(
        H, ids, "Slowest tools (p95, 3+ calls)",
        f"{ok} | stats by (toolName) count() calls, quantile(0.95, durationMs) p95, max(durationMs) max "
        f"| filter calls:>=3 | sort by (p95 desc) | limit 10",
        12, y, 12, 8, ("toolName", "Tool"),
        [("p95", "p95", "ms", lat), ("max", "Max", "ms", lat), ("calls", "Calls", "n", None)],
        desc="Where the waiting is. Tools called fewer than 3 times are left out."))
    return P, y + 8


# -- Friendly Actual Budget -------------------------------------------------------------------------------------

def friendly_actual_budget(H, ids, y):
    base = "service.name:friendly-actual-budget status:in(completed,failed) durationMs:*"
    lat = _lat_thr(H, 1500, 4000)
    P = [_section(H, ids, y, "API latency")]
    y += 1
    P.append(_hero(H, ids, "Operations", f"{base} | stats count() calls", 0, y, 6, 5, H.steps((H.BLUE, None)),
                   desc="Timed operations (ingest, queue, Actual Budget calls) in the selected range."))
    P.append(_hero(H, ids, "Receipts confirmed",
                   "service.name:friendly-actual-budget action:transaction-confirmed status:completed | stats count() n",
                   6, y, 6, 5, H.steps((H.BLUE, None)), desc="Transactions that reached Actual Budget."))
    P.append(_hero(H, ids, "Failed", f"{base} status:failed | stats count() n", 12, y, 6, 5,
                   H.steps((H.GREEN, None), (H.ORANGE, 1), (H.RED, 5)), desc="Operations that ended failed."))
    P.append(_hero(H, ids, "Slow calls (p95)", f"{base} | stats quantile(0.95, durationMs) p95", 18, y, 6, 5, lat,
                   unit="ms", desc="95% of operations finish faster than this.", no_value="n/a"))
    y += 5

    P.append(_table(
        H, ids, "Latency per API call",
        f"{base} | stats by (action) count() calls, count() if (status:failed) failed, quantile(0.5, durationMs) p50, "
        f"quantile(0.95, durationMs) p95, max(durationMs) max | sort by (p95 desc) | limit 30",
        0, y, 14, 10, ("action", "Operation"),
        [("calls", "Calls", "bar", None), ("failed", "Failed", "fail", None), ("p50", "Median", "ms", lat),
         ("p95", "p95", "ms", lat), ("max", "Max", "ms", lat)],
        desc="One row per logged operation (actual-connect, queue-enqueue, ingest-wallet...), slowest first."))
    P.append(H.timeseries(
        ids, "p95 latency by operation",
        [H.lq(f"{base} | stats by (action) quantile(0.95, durationMs) p95", "A", "statsRange", "1h")],
        14, y, 10, 10, unit="ms", desc="Hourly p95 per operation."))
    y += 10

    P.append(_table(
        H, ids, "HTTP routes",
        "service.name:friendly-actual-budget action:http-request | stats by (method, path) count() calls, "
        "count() if (status:failed) failed, quantile(0.5, durationMs) p50, quantile(0.95, durationMs) p95 "
        "| sort by (calls desc) | limit 20",
        0, y, 14, 8, ("path", "Route"),
        [("method", "Method", "n", None), ("calls", "Calls", "bar", None), ("failed", "Failed", "fail", None),
         ("p50", "Median", "ms", lat), ("p95", "p95", "ms", lat)],
        desc="Per-route request counts and latency from the access log (needs the request-logging release)."))
    P.append(H.timeseries(
        ids, "Receipts per hour",
        [H.lq("service.name:friendly-actual-budget action:wallet-ingest-queued | stats count() n", "A", "statsRange", "1h"),
         H.lq("service.name:friendly-actual-budget action:transaction-confirmed | stats count() n", "B", "statsRange", "1h")],
        14, y, 10, 8, overrides=[H.ref_override("A", "Queued", H.BLUE), H.ref_override("B", "Confirmed", H.GREEN)],
        desc="Receipts queued vs confirmed. A gap means receipts are stuck in the queue."))
    return P, y + 8


# -- Sentence Gym -----------------------------------------------------------------------------------------------

def sentence_gym(H, ids, y):
    ns = '{kubernetes.pod_namespace="sentence-gym"}'
    act = f"{ns} event:user.action"
    api = f"{ns} event:api.request"
    lat = _lat_thr(H, 1000, 3000)
    P = [_section(H, ids, y, "What learners do")]
    y += 1
    P.append(_hero(H, ids, "Actions", f"{act} | stats count() n", 0, y, 6, 5, H.steps((H.BLUE, None)),
                   desc="User actions logged by the app (event user.action) in the selected range.", no_value="n/a"))
    P.append(_hero(H, ids, "Failed actions", f"{act} outcome:failed | stats count() n", 6, y, 6, 5,
                   H.steps((H.GREEN, None), (H.ORANGE, 1), (H.RED, 5)), desc="Actions that ended failed."))
    P.append(_hero(H, ids, "API requests", f"{api} | stats count() n", 12, y, 6, 5, H.steps((H.BLUE, None)),
                   desc="Server API requests (event api.request)."))
    P.append(_hero(H, ids, "Slow API (p95)", f"{api} | stats quantile(0.95, duration_ms) p95", 18, y, 6, 5, lat,
                   unit="ms", desc="95% of API requests finish faster than this.", no_value="n/a"))
    y += 5

    P.append(_table(
        H, ids, "Actions leaderboard",
        f"{act} | stats by (action) count() times, count() if (outcome:failed) failed, quantile(0.5, duration_ms) p50, "
        f"quantile(0.95, duration_ms) p95 | sort by (times desc) | limit 30",
        0, y, 12, 10, ("action", "Action"),
        [("times", "Times", "bar", None), ("failed", "Failed", "fail", None), ("p50", "Median", "ms", lat),
         ("p95", "p95", "ms", lat)],
        desc="How many times each action was performed, most used first.", no_value="Waiting for user.action events"))
    P.append(H.timeseries(
        ids, "Actions per hour", [H.lq(f"{act} | stats by (action) count() n", "A", "statsRange", "1h")],
        12, y, 12, 10, stack=True, desc="User actions per hour, stacked by action."))
    y += 10

    P.append(_table(
        H, ids, "API routes",
        f"{api} | stats by (route) count() calls, quantile(0.5, duration_ms) p50, quantile(0.95, duration_ms) p95 "
        f"| sort by (calls desc) | limit 20",
        0, y, 12, 8, ("route", "Route"),
        [("calls", "Calls", "bar", None), ("p50", "Median", "ms", lat), ("p95", "p95", "ms", lat)],
        desc="Server routes: request count and latency."))
    P.append(H.timeseries(
        ids, "API latency per hour",
        [H.lq(f"{api} | stats quantile(0.5, duration_ms) p50, quantile(0.95, duration_ms) p95", "A", "statsRange", "1h")],
        12, y, 12, 8, unit="ms", desc="Median and p95 API latency, hourly."))
    return P, y + 8


# -- Vegapunk ---------------------------------------------------------------------------------------------------

def vegapunk(H, ids, y):
    q = '{kubernetes.pod_namespace="vegapunk"} event:query.completed'
    ok = f"{q} outcome:ok"
    lat = _lat_thr(H, 10000, 30000)
    P = [_section(H, ids, y, "Questions")]
    y += 1
    P.append(_hero(H, ids, "Questions asked", f"{q} | stats count() n", 0, y, 8, 7, H.steps((H.BLUE, None)),
                   desc="Answers produced by the web UI, MCP and API in the selected range. Change the range for 7d or 30d totals.",
                   text=HUGE, no_value="n/a"))
    P.append(_hero(H, ids, "Typical answer time", f"{ok} | stats quantile(0.5, duration_ms) p50", 8, y, 5, 7, lat,
                   unit="ms", desc="Half of answers arrive faster than this.", no_value="n/a"))
    P.append(_hero(H, ids, "Slow answers (p95)", f"{ok} | stats quantile(0.95, duration_ms) p95", 13, y, 5, 7, lat,
                   unit="ms", desc="95% of answers arrive faster than this.", no_value="n/a"))
    P.append(_hero(H, ids, "Not found", f"{q} | stats count() if (outcome:not_found) nf, count() total "
                   f"| filter total:>0 | math nf*100/total as pct | fields pct", 18, y, 6, 7,
                   H.steps((H.GREEN, None), (H.ORANGE, 15), (H.RED, 35)), unit="percent", decimals=0,
                   desc="Share of questions with no relevant document found.", no_value="n/a"))
    y += 7

    P.append(H.timeseries(
        ids, "Questions per hour", [H.lq(f"{q} | stats by (channel) count() n", "A", "statsRange", "1h")],
        0, y, 12, 8, stack=True, desc="Questions per hour, stacked by channel (web, mcp, api)."))
    P.append(H.timeseries(
        ids, "Answer time per hour",
        [H.lq(f"{ok} | stats quantile(0.5, duration_ms) p50, quantile(0.95, duration_ms) p95", "A", "statsRange", "1h")],
        12, y, 12, 8, unit="ms", desc="Median and p95 answer time, hourly."))
    y += 8

    P.append(_table(
        H, ids, "By channel",
        f"{q} | stats by (channel) count() questions, count() if (outcome:failed) failed, "
        f"quantile(0.5, duration_ms) p50, quantile(0.95, duration_ms) p95 | sort by (questions desc)",
        0, y, 24, 5, ("channel", "Channel"),
        [("questions", "Questions", "bar", None), ("failed", "Failed", "fail", None), ("p50", "Median", "ms", lat),
         ("p95", "p95", "ms", lat)],
        desc="Where questions come from and how fast each channel is answered.", no_value="Waiting for query.completed events"))
    return P, y + 5


BUILDERS = {
    "poke-hub": poke_hub,
    "friendly-actual-budget": friendly_actual_budget,
    "sentence-gym": sentence_gym,
    "vegapunk": vegapunk,
}
