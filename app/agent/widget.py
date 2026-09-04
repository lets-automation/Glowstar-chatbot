"""
widget.py
---------
Inline visual-widget rendering ("Claude artifacts, but ours").

The model can call the `show_widget` tool to emit a self-contained HTML/SVG
fragment instead of describing a visual in prose. The fragment is rendered by
the frontend inside a sandboxed, null-origin iframe (see
frontend/src/SandboxedWidget.jsx) — it NEVER touches our own DOM.

This module holds the two provider-agnostic pieces, mirroring how tools.py
exposes TOOL_SPECS and RULES:
  - SHOW_WIDGET_TOOL_SPEC : the tool definition (same {name, description,
                            schema} shape as tools.TOOL_SPECS, so each backend
                            wraps it in its own format).
  - WIDGET_CORE_PROMPT    : which visual tool to use and - just as
                            important - when to use none. Merged into the
                            system prompt on EVERY chat call.
  - WIDGET_DESIGN_PROMPT  : the design-system rules for hand-written
                            show_widget fragments. ~1k tokens that only that
                            one tool ever reads, so needs_design_rules() /
                            visual_prompt_for() gate it on the question and
                            the backends append it dead last. The CSS-variable
                            palette it references is defined (and themeable) in
                            the iframe host: frontend/src/SandboxedWidget.jsx.

The capture of the widget code itself happens in the backend agent loops
(anthropic_backend.py / groq_backend.py), because the tool's "result" is a UI
artifact shown to the user, not text fed back to the model.
"""

import re

# Same shape as the entries in tools.TOOL_SPECS. Each backend converts this into
# its provider-specific tool format alongside the DB tools.
SHOW_WIDGET_TOOL_SPEC = {
    "name": "show_widget",
    "description": (
        "Render inline visual content (HTML or SVG) in the chat - custom "
        "visuals, calculators, diagrams, forms, interactive explainers. For a "
        "simple chart use show_chart; for an analytics dashboard use "
        "show_dashboard - NOT this tool. "
        "Call this INSTEAD of writing the visual as text. Rules: output a "
        "self-contained fragment with NO <!doctype>, <html>, <head>, or <body> "
        "tags. Use the provided CSS variables for all theming so it works in "
        "light and dark mode. Only load libraries from the allowlisted CDNs. "
        "Put explanatory prose in your normal text response, NOT inside the "
        "widget."
    ),
    "schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "short snake_case id, also the download filename",
            },
            "widget_code": {
                "type": "string",
                "description": "HTML or SVG fragment",
            },
        },
        "required": ["title", "widget_code"],
    },
}


# Deterministic chart tool: for a standard single-series chart the model only
# supplies the DATA (labels + values); the HTML/JS comes from the fixed template
# in build_chart_html() below, so it can never be broken JS. This exists because
# free-tier models routinely emit invalid Chart.js fragments via show_widget
# (missing the library <script>, unbalanced braces...) which render as a blank
# box. show_widget remains for custom visuals beyond a simple chart.
SHOW_CHART_TOOL_SPEC = {
    "name": "show_chart",
    "description": (
        "Draw a standard on-screen chart in the chat from data you already "
        "have. PREFER this over show_widget for any simple bar / horizontal "
        "bar / line / pie chart of one data series: you pass only the labels "
        "and numbers and the app renders a correct, styled chart. Use "
        "show_widget only for visuals this cannot express (multi-series, "
        "dashboards, diagrams, interactive tools)."
    ),
    "schema": {
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["bar", "horizontal_bar", "line", "pie"],
                "description": "The kind of chart.",
            },
            "title": {"type": "string", "description": "Short chart title."},
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Category labels, one per data point.",
            },
            "values": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Numeric values, same order/length as labels.",
            },
            "series_label": {
                "type": "string",
                "description": "What the numbers are (e.g. 'Total incentive').",
            },
        },
        "required": ["chart_type", "labels", "values"],
    },
}

# Deterministic dashboard tool: a full analytics ARTIFACT (KPI tiles + trend +
# breakdown sections) where the model only supplies the DATA it computed via
# run_sql; the polished HTML comes from build_dashboard_html() below. Exists for
# the same reason as show_chart: free-tier models cannot reliably hand-write a
# dashboard page, but they CAN fill in a structured JSON of numbers.
SHOW_DASHBOARD_TOOL_SPEC = {
    "name": "show_dashboard",
    "description": (
        "Render a polished analytics DASHBOARD in the chat: a row of KPI stat "
        "tiles plus optional chart sections (trend line, bar/horizontal-bar "
        "breakdown, pie). Use it when the user asks for analytics, an overview, "
        "a dashboard, a performance/analysis summary of the company, a period, "
        "a kapan, a department, or an employee. FIRST run the run_sql queries "
        "you need (headline totals, a trend, a breakdown), THEN call this ONCE "
        "with the numbers you actually retrieved - every value MUST come from "
        "run_sql results in this conversation, never invented. Prefer this over "
        "show_widget/show_chart for any multi-part analytics view."
    ),
    "schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Dashboard heading, e.g. 'GlowStar production analytics'."},
            "subtitle": {"type": "string", "description": "Period or scope, e.g. 'June 2026' or 'Kapan NS26'."},
            "tiles": {
                "type": "array",
                "description": "2-6 KPI stat tiles (the headline numbers).",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "Short metric name, e.g. 'Packets finished'."},
                        "value": {"type": ["number", "string"], "description": "The metric value. Number preferred; string only when pre-formatted (e.g. '73.2%')."},
                        "unit": {"type": "string", "description": "Optional unit shown after the value, e.g. 'ct', 'pcs', 'points'."},
                        "delta": {"type": "string", "description": "Optional change vs previous period, e.g. '+12.4% vs May'. Start with + or -."},
                        "delta_good": {"type": "boolean", "description": "Whether this change is good (green) or bad (red)."},
                    },
                    "required": ["label", "value"],
                },
            },
            "sections": {
                "type": "array",
                "description": "0-3 chart sections below the tiles.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["bar", "horizontal_bar", "line", "pie"],
                            "description": "line = trend over time; horizontal_bar = ranked breakdown; bar = category comparison; pie = share of total.",
                        },
                        "title": {"type": "string", "description": "Section heading, e.g. 'Monthly production trend'."},
                        "labels": {"type": "array", "items": {"type": ["string", "number"]}, "description": "Category labels (strings preferred; numbers accepted)."},
                        "values": {"type": "array", "items": {"type": ["number", "string"]}, "description": "Numbers, same order/length as labels."},
                        "series_label": {"type": "string", "description": "What the numbers are, e.g. 'Carats polished'."},
                    },
                    "required": ["type", "title", "labels", "values"],
                },
            },
        },
        "required": ["title", "tiles"],
    },
}


# Categorical palette from the design rules (pie slices use it in order).
_PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
            "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]

_CHARTJS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"


def build_chart_html(args: dict) -> str:
    """Render a guaranteed-valid Chart.js fragment from plain data."""
    import json as _json

    chart_type = str(args.get("chart_type") or "bar")
    title = str(args.get("title") or "Chart")
    labels = [str(x) for x in (args.get("labels") or [])]
    values = [float(x) for x in (args.get("values") or [])]
    if not labels or not values:
        raise ValueError("labels and values must be non-empty")
    if len(labels) != len(values):
        raise ValueError("labels and values must have the same length")
    series = str(args.get("series_label") or title)

    horizontal = chart_type == "horizontal_bar"
    js_type = {"horizontal_bar": "bar", "pie": "pie", "line": "line"}.get(chart_type, "bar")
    height = max(240, 40 * len(labels) + 80) if horizontal else 300
    colors = _PALETTE[: len(values)] if js_type == "pie" else _PALETTE[0]

    cfg = {
        "type": js_type,
        "data": {
            "labels": labels,
            "datasets": [{
                "label": series,
                "data": values,
                "backgroundColor": colors,
                "borderColor": "#ffffff" if js_type == "pie" else _PALETTE[0],
                "borderWidth": 1 if js_type == "pie" else 0,
                "tension": 0.3,
                "fill": False,
            }],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "indexAxis": "y" if horizontal else "x",
            "plugins": {"legend": {"display": js_type == "pie"}},
        },
    }
    if js_type != "pie":
        tick = {"ticks": {"color": "#898781", "autoSkip": False}}
        cfg["options"]["scales"] = {"x": dict(tick), "y": dict(tick)}

    import html as _htmlmod

    safe_title = _htmlmod.escape(title)
    aria = _htmlmod.escape(f"{chart_type} chart: {title}")
    # Escape EVERY '<' as < (decodes back to '<' inside JS strings): plain
    # '</'-only escaping still let '<!--<script>' flip the HTML parser into the
    # script-data-double-escaped state and swallow the following script tag.
    cfg_js = _json.dumps(cfg).replace("<", "\\u003c")
    return (
        f'<h2 class="sr-only">{safe_title}</h2>'
        f'<div style="position:relative;height:{height}px">'
        f'<canvas id="gs-chart" role="img" aria-label="{aria}">{safe_title}</canvas></div>'
        f'<script src="{_CHARTJS_CDN}"></script>'
        "<script>new Chart(document.getElementById('gs-chart'),"
        f"{cfg_js});</script>"
    )


def _fmt_indian(num) -> str:
    """Format a number with Indian digit grouping (12,34,567.89).

    Ints stay exact (no float() detour - float corrupts integers above 2^53);
    floats round FIRST so e.g. 2.999 -> 3 (splitting before rounding would
    give whole=2 + frac=1.00 -> "21.00").
    """
    neg = num < 0
    if isinstance(num, int):
        whole, frac = abs(num), 0.0
    else:
        num = round(abs(num), 2)
        whole = int(num)
        frac = round(num - whole, 2)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    if frac:
        s += f"{frac:.2f}".lstrip("0")  # ".5" -> "0.50" handled: '0.50'.lstrip('0') == '.50'
    # Sign AFTER rounding so -0.004 renders "0", not "-0".
    return ("-" if neg and (whole or frac) else "") + s


def build_dashboard_html(args: dict) -> str:
    """
    Render a guaranteed-valid analytics dashboard fragment from plain data:
    KPI stat tiles + optional chart sections. Same contract as build_chart_html:
    the model supplies only data; every string is escaped, every number coerced,
    so the fragment can never be broken or carry injected markup. Raises
    ValueError on bad input (the backends feed the message back so the model
    can retry).
    """
    import html as _htmlmod
    import json as _json

    def esc(x):
        return _htmlmod.escape(str(x))

    title = str(args.get("title") or "Dashboard")
    subtitle = str(args.get("subtitle") or "")
    tiles = args.get("tiles") or []
    sections = args.get("sections") or []
    if not isinstance(tiles, list) or not tiles:
        raise ValueError("tiles must be a non-empty array of {label, value}")
    if not isinstance(sections, list):
        raise ValueError("sections must be an array")
    # Tolerate more than the spec asks for rather than silently dropping data
    # the model computed: cap at the same limits as the PDF/Excel export
    # (12 tiles / 6 sections) so the screen and the download always match.
    tiles = tiles[:12]
    sections = sections[:6]

    # ---- KPI tiles -------------------------------------------------------
    tile_html = []
    for t in tiles:
        if not isinstance(t, dict) or "label" not in t or "value" not in t:
            raise ValueError("each tile needs at least {label, value}")
        label = esc(t["label"])
        raw_val = t["value"]
        if raw_val is None:
            value = "&#8212;"  # em dash, not the text "None"
        elif isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
            value = _fmt_indian(raw_val)  # ints stay ints (exact above 2^53)
        elif isinstance(raw_val, str) and re.fullmatch(r"-?\d+(\.\d+)?", raw_val.strip()):
            # A plain numeric string (models often send numbers as strings).
            sv = raw_val.strip()
            value = _fmt_indian(int(sv) if "." not in sv else float(sv))
        else:
            value = esc(raw_val)
        unit = esc(t["unit"]) if t.get("unit") else ""
        unit_html = f' <span style="font-size:13px;color:var(--text-muted)">{unit}</span>' if unit else ""
        delta_html = ""
        if t.get("delta"):
            d = str(t["delta"]).strip()
            arrow = "▼" if d.startswith("-") else "▲"
            dg = t.get("delta_good")
            color = ("var(--text-success)" if dg else "var(--text-danger)") if isinstance(dg, bool) else "var(--text-muted)"
            delta_html = (
                f'<div style="font-size:12px;margin-top:4px;color:{color}">'
                f'{arrow} {esc(d)}</div>'
            )
        tile_html.append(
            '<div style="background:var(--surface-1);border-radius:var(--radius);padding:1rem">'
            f'<div style="font-size:13px;color:var(--text-muted)">{label}</div>'
            f'<div style="font-size:24px;font-weight:500;margin-top:2px">{value}{unit_html}</div>'
            f"{delta_html}</div>"
        )

    # ---- Sections --------------------------------------------------------
    section_html = []
    chart_scripts = []  # (canvas_id, cfg_json) - all emitted in ONE script at the end
    needs_chartjs = False
    for i, s in enumerate(sections):
        if not isinstance(s, dict):
            raise ValueError("each section must be an object")
        stype = str(s.get("type") or "bar")
        raw_title = str(s.get("title") or "Breakdown")
        stitle = esc(raw_title)
        labels = ["–" if x is None else str(x) for x in (s.get("labels") or [])]
        values_raw = s.get("values") or []
        try:
            values = [float(x) for x in values_raw]
        except (TypeError, ValueError):
            raise ValueError(f"section '{s.get('title')}': values must all be numbers")
        if not labels or not values or len(labels) != len(values):
            raise ValueError(
                f"section '{s.get('title')}': labels and values must be non-empty and the same length"
            )
        # Fallback from the RAW title (stitle is already escaped - using it here
        # would double-escape '&' etc. in the caption and chart legend).
        series = str(s.get("series_label") or raw_title)

        if stype == "horizontal_bar":
            # Pure-CSS ranked bars (no JS - can't break): label, track, value.
            shown_l, shown_v = labels[:15], values[:15]
            hidden = len(values) - len(shown_v)
            # Scale against the RENDERED rows only - scaling against a hidden
            # tail row would flatten every visible bar toward the 2% minimum.
            vmax = max((abs(v) for v in shown_v), default=1) or 1
            rows = []
            for lab, val in zip(shown_l, shown_v):
                pct = max(2, round(abs(val) / vmax * 100))
                color = _PALETTE[0]
                rows.append(
                    '<div style="display:flex;align-items:center;gap:10px;margin:7px 0">'
                    f'<div style="flex:0 0 34%;font-size:13px;color:var(--text-secondary);'
                    f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{esc(lab)}</div>'
                    '<div style="flex:1;background:var(--surface-0);border-radius:99px;height:8px;overflow:hidden">'
                    f'<div style="width:{pct}%;height:100%;border-radius:99px;background:{color}"></div></div>'
                    f'<div style="flex:0 0 72px;text-align:right;font-size:13px;font-weight:500">'
                    f"{esc(_fmt_indian(val))}</div></div>"
                )
            if hidden > 0:  # never silently truncate
                rows.append(
                    f'<div style="font-size:12px;color:var(--text-muted);margin-top:6px">'
                    f"+{hidden} more not shown</div>"
                )
            body = "".join(rows)
            section_html.append(
                '<div style="background:var(--surface-2);border:0.5px solid var(--border);'
                'border-radius:12px;padding:1rem 1.25rem;margin-top:12px">'
                f'<h3 style="margin:0 0 6px 0">{stitle}</h3>'
                f'<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">{esc(series)}</div>'
                f"{body}</div>"
            )
            continue

        # Chart.js section (line / bar / pie) - same guaranteed-valid approach
        # as build_chart_html.
        needs_chartjs = True
        js_type = {"pie": "pie", "line": "line"}.get(stype, "bar")
        if js_type == "pie" and len(values) > 8:
            # Beyond the 8-color palette a pie degrades into unreadable gray
            # slices. Keep the 7 largest, aggregate the tail into "Other"
            # (a SUM, so the total stays exact - nothing silently dropped).
            pairs = sorted(zip(labels, values), key=lambda p: abs(p[1]), reverse=True)
            labels = [p[0] for p in pairs[:7]] + ["Other"]
            values = [p[1] for p in pairs[:7]] + [round(sum(p[1] for p in pairs[7:]), 2)]
        colors = _PALETTE[: len(values)] if js_type == "pie" else _PALETTE[0]
        cid = f"gs-dash-{i}"
        cfg = {
            "type": js_type,
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": series,
                    "data": values,
                    "backgroundColor": colors,
                    "borderColor": "#ffffff" if js_type == "pie" else _PALETTE[0],
                    "borderWidth": 1 if js_type == "pie" else 0,
                    "tension": 0.3,
                    "fill": False,
                }],
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {"legend": {"display": js_type == "pie"}},
            },
        }
        if js_type == "line":
            cfg["data"]["datasets"][0]["borderWidth"] = 2
        if js_type != "pie":
            tick = {"ticks": {"color": "#898781", "autoSkip": False}}
            cfg["options"]["scales"] = {"x": dict(tick), "y": dict(tick)}
        aria = esc(f"{stype} chart: {s.get('title') or 'Breakdown'}")
        section_html.append(
            '<div style="background:var(--surface-2);border:0.5px solid var(--border);'
            'border-radius:12px;padding:1rem 1.25rem;margin-top:12px">'
            f'<h3 style="margin:0 0 10px 0">{stitle}</h3>'
            '<div style="position:relative;height:260px">'
            f'<canvas id="{cid}" role="img" aria-label="{aria}">{stitle}</canvas></div></div>'
        )
        # Escape EVERY '<' (not just '</') as <: inside JSON string
        # literals it decodes back to '<' at JS parse time, but sequences like
        # '<!--<script>' can no longer flip the HTML parser into the
        # script-data-double-escaped state and swallow the host bridge script.
        chart_scripts.append((cid, _json.dumps(cfg).replace("<", "\\u003c")))

    # ---- Assemble (streaming-safe: content first, scripts LAST) ----------
    subtitle_html = (
        f'<div style="font-size:13px;color:var(--text-muted)">{esc(subtitle)}</div>'
        if subtitle else ""
    )
    parts = [
        f'<h2 class="sr-only">{esc(f"Analytics dashboard: {title}")}</h2>',
        '<div style="display:flex;align-items:baseline;justify-content:space-between;'
        'gap:12px;flex-wrap:wrap;margin-bottom:12px">'
        f'<h2 style="margin:0">{esc(title)}</h2>{subtitle_html}</div>',
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));'
        f'gap:12px">{"".join(tile_html)}</div>',
        "".join(section_html),
    ]
    if needs_chartjs:
        parts.append(f'<script src="{_CHARTJS_CDN}"></script>')
        draws = "".join(
            f"new Chart(document.getElementById('{cid}'),{cfg});"
            for cid, cfg in chart_scripts
        )
        parts.append(f"<script>{draws}</script>")
    return "".join(parts)


def ensure_chart_lib(code: str) -> str:
    """
    Repair a model-written show_widget fragment that uses Chart.js without
    loading it (a common weak-model mistake that renders as a blank box).
    """
    if not code:
        return code
    uses_chart = "new Chart(" in code or "new Chart (" in code
    loads_lib = "chart.js" in code.lower() or "chart.umd" in code.lower()
    if uses_chart and not loads_lib:
        return f'<script src="{_CHARTJS_CDN}"></script>\n' + code
    return code


# ---------------------------------------------------------------------------
# THE VISUAL PROMPT, IN TWO PIECES
#
# This used to be one 2,023-token block merged into the system prompt on EVERY
# call, on every provider, on every round of the tool loop - and one report
# question spends ~6 rounds (see the measurement in tools.dynamic_schema_for).
#
# ~70% of those tokens are a DESIGN SYSTEM that applies to exactly one of the
# three tools. show_chart and show_dashboard never need it: their HTML comes
# from build_chart_html() / build_dashboard_html() above, so the palette, the
# type scale, the component specs and the Chart.js wiring are OURS, not the
# model's. Only show_widget - the rare custom-visual path - reads those rules.
# So the block is split in two:
#
#   WIDGET_CORE_PROMPT    always on. Which tool to use, when to draw NOTHING,
#                         and the handful of rules whose absence turns a widget
#                         into a blank box or invisible dark-mode text.
#   WIDGET_DESIGN_PROMPT  appended only when needs_design_rules() sees
#                         custom-visual intent in the question.
#
# PLACEMENT MATTERS AS MUCH AS SIZE. The design block is appended DEAD LAST,
# after the per-question schema. Prompt caching matches a PREFIX, so a block
# that switches on and off in the MIDDLE would un-cache everything behind it -
# the same trap documented at the top of tools.dynamic_schema_for(). Put in
# front of the schema it would flip the cache key of ~20k tokens on every
# question that happened to mention a diagram.
#
# The CSS variables referenced below are defined in
# frontend/src/SandboxedWidget.jsx (the iframe host); they auto-adapt to light
# and dark mode. Keep the rules verbatim - they prevent the broken and
# inconsistent output you would otherwise get.
# ---------------------------------------------------------------------------
WIDGET_CORE_PROMPT = """
# Visual output: three tools, and when to use none of them

Text is the default. Most answers need no visual at all - a sentence, or a Markdown table
when there are rows to show, IS the best answer.

Your tools:
- show_chart      one standard chart (bar, horizontal_bar, line, pie): you pass chart_type +
                  labels + values, the app renders it. NEVER hand-write chart code.
- show_dashboard  an analytics view: 3-6 KPI tiles plus 1-3 chart sections.
- show_widget     a CUSTOM visual ONLY - diagram, process flow, timeline, multi-series or
                  non-standard chart, form, calculator, interactive explainer. Anything the
                  other two can express MUST use them instead.

# Do NOT draw anything (this is the normal case)
Answer in plain text, with a Markdown table when there are rows, for:
- a single number, total, count, average, percentage, yes/no, or a lookup
- an identity or profile row - a name, code, department, date, status
- a REPORT or a listing: a report is a TABLE of detail rows, never a chart
- fewer than 4 data points, or values that are not comparable with each other
- an explanation, a definition, a how-to, small talk, an error, or a refusal
A chart that restates a number already in your sentence adds nothing. Not drawing is the
safe default: when in doubt, leave it out.

# Draw when you are asked
If the user asks you to draw, plot, chart, graph, visualize, diagram or render something,
CALL the tool. Never describe the visual in words, and NEVER write a placeholder like
"[Chart image: ...]" or "(see chart below)" - that is a failure; the tool call IS the chart.

# Draw for an analytics request
When the user asks for ANALYTICS, an OVERVIEW, a DASHBOARD, or a PERFORMANCE / ANALYSIS
summary (of the company, a period, a kapan, a department, an employee):
1) run the 2-4 aggregate run_sql queries you need - the headline totals, ideally a trend over
   time, and a breakdown by category;
2) then call show_dashboard ONCE with 3-6 KPI tiles (label + value + unit; add a delta vs the
   previous period when you queried it) and 1-3 sections (line = trend, horizontal_bar =
   ranked breakdown, bar = comparison, pie = share).
Prefer one dashboard over several separate charts, and keep your text short - the dashboard
carries the numbers, your text carries the insight. NEVER hand-write a dashboard with
show_widget; show_dashboard renders it correctly.

# Draw unasked - rarely, and at most once
Add a show_chart the user did not ask for ONLY when the point of the answer is a shape they
cannot see in the numbers: 4 or more comparable categories being ranked or compared, or a
trend across 4 or more periods. One chart per answer, never two. If the answer is already
clear from the table or the sentence, do not add one.

# Every number must be real
Each tile, label and value MUST come from a run_sql result in THIS conversation. A chart or
dashboard with invented numbers is the worst possible failure. If the user handed you the
numbers in their message, use those - do not run a query for data you were given.

# show_widget fragments: ignoring these breaks the render
- Fragment only, no <!doctype>/<html>/<head>/<body> - the host wraps it. Starts with <svg =
  SVG, otherwise HTML.
- NEVER localStorage/sessionStorage (blocked, throws - keep state in memory) and NEVER
  position:fixed (the iframe auto-sizes; fixed elements collapse it).
- Load external files ONLY from cdnjs.cloudflare.com, cdn.jsdelivr.net, unpkg.com, esm.sh,
  fonts.googleapis.com, fonts.gstatic.com. Anything else is blocked silently.
- NEVER hardcode a color: var(--surface-2)/var(--surface-1) backgrounds, var(--text-primary)/
  var(--text-secondary) text, var(--border) lines. They adapt to dark mode, where color:#333
  is invisible. Chart data: #2a78d6, then #1baf7a, then #eda100.
- Round EVERY displayed number. No emoji, gradients, shadows, or text under 11px.
- Explanation goes in your text reply; the widget holds ONLY the visual.

You cannot create downloadable files. When asked to export or download, answer with the data
and point the user at the Export buttons below your answer.
"""


# Only reaches the model when needs_design_rules() fires - i.e. the question is
# asking for something show_chart / show_dashboard cannot render.
WIDGET_DESIGN_PROMPT = """
# show_widget design system
These rules apply ONLY to an HTML/SVG fragment you write yourself with show_widget.
show_chart and show_dashboard are rendered by the app and need none of this.

# Theming - use these CSS variables, never hardcode colors
Surfaces: --surface-2 (card white), --surface-1 (raised), --surface-0 (page);
  tints --bg-accent, --bg-success, --bg-warning, --bg-danger
Text: --text-primary, --text-secondary, --text-muted;
  roles --text-accent, --text-success, --text-warning, --text-danger
Borders: --border (hairline), --border-strong; roles --border-accent etc.
Type: --font-sans, --font-voice (serif, editorial only), --font-mono
Layout: --radius (8px controls; use 12px for cards), --pad-sm/md/lg, --gap-xs/sm/md/lg
All variables auto-adapt to light and dark mode. NEVER write color:#333 - invisible in dark.
Mental test before finishing: if the background were near-black, is every text element readable?

# Color palette (categorical - assign in this fixed order, NEVER cycle like a rainbow)
Color encodes meaning, not sequence. Group by category; same type = same color. Use 2-3 colors
max. Canvas cannot read CSS vars, so use these hex values directly in chart datasets:
  1 blue #2a78d6  2 teal #1baf7a  3 amber #eda100  4 green #008300
  5 violet #4a3aa7  6 red #e34948  7 pink #e87ba4  8 orange #eb6834
Sequential (magnitude): one hue, light->dark. Diverging (above/below a baseline): blue<->red with a
neutral gray midpoint, never a hue at the midpoint. Status (good/warn/serious/critical):
  #0ca30c / #fab219 / #ec835a / #d03b3b - reserved, always paired with an icon+label, never
  color alone. Text on a colored fill uses the darkest shade of that same hue, never black.

# Typography
Headings: h1 22px, h2 18px, h3 16px - all font-weight:500. Body 16px / line-height 1.7.
Two weights only: 400 and 500. Never 600/700. Sentence case everywhere (labels, SVG text too).
No mid-sentence bold - use code style for entity/function names.

# Components
Metric card (summary numbers): background var(--surface-1), no border, border-radius var(--radius),
  padding 1rem; 13px muted label above, 24px/500 value below. Grids of 2-4, gap 12px.
Raised card (a bounded object): background var(--surface-2), 0.5px solid var(--border),
  border-radius 12px, padding ~1rem 1.25rem.
Comparison: card grid, one accent card uses border:2px solid var(--border-accent) (the only
  exception to 0.5px borders). Output real comparison TABLES as markdown in your text, not here.

# Charts (Chart.js)
- Wrap <canvas> in a <div> with position:relative and an explicit height. Set height ONLY on the
  wrapper, never on the canvas. Use responsive:true, maintainAspectRatio:false.
- Every <canvas> needs role="img", a descriptive aria-label, and fallback text between the tags.
- Canvas cannot resolve CSS vars - use hex. For dark mode read prefers-color-scheme and pick
  tick/grid colors (muted #898781; grid #e1e0d9 light / #2c2c2a dark).
- Disable the default legend (plugins.legend.display=false) and build a small custom HTML legend
  with colored squares + values. Never rely on color alone - add a dash/marker/pattern cue.
- Horizontal bars: wrapper height >= bars*40 + 80. For <=12 categories needing every label,
  set scales.x.ticks autoSkip:false, maxRotation:45.

# Streaming-safe structure
Order: short <style> (or inline styles) -> content HTML -> <script> LAST. Scripts only execute
after streaming completes. Prefer inline style="" on controls so they look right mid-stream.
Load libraries via <script src> (UMD global), then a following plain <script> uses the global.

# Accessibility
HTML widgets begin with a visually-hidden <h2 class="sr-only"> one-sentence summary.
SVG uses role="img" with <title> and <desc>.

# Interactivity
A global function sendPrompt(text) is available - it sends a message to chat as if the user
typed it. Use it for actions that need the model to think (drill-downs, "explain this"). Handle
filtering, sorting, toggling, and math in plain JS instead. Links via <a href> just work.
"""


# ---------------------------------------------------------------------------
# THE GATE
#
# Decided in CODE, before any model call - the same family as smalltalk_gate,
# date_gate and note_router. An LLM "router" pre-call was considered and
# rejected: it adds a whole round trip to the front of every question, and on
# the free Gemini tier (20 requests/day) it would halve how many questions the
# bot can answer in a day. It also cannot make the call it would be asked to
# make - whether a RESULT deserves a chart depends on the rows, which do not
# exist until run_sql has run inside the tool loop.
#
# It matches CUSTOM-visual intent only. Deliberately NOT in the list: chart,
# graph, plot, dashboard, analytics, report, overview. Those are served by
# show_chart / show_dashboard, which render from our own templates and need
# none of these rules - and they are what this bot is actually asked for all
# day ("report of M4167", "how many packets on jangad", "production analytics
# for June"). That exclusion is the whole reason the split pays.
#
# Biased towards firing: a false positive costs ~1.4k tokens on ONE question, a
# false negative costs an uglier widget. Ambiguous terms go in. The core prompt
# still carries every rule whose absence would break the render outright, so a
# miss degrades the styling, never the output.
# ---------------------------------------------------------------------------
_CUSTOM_VISUAL_RE = re.compile(
    r"\b("
    # structure / process pictures
    r"diagrams?|flow ?charts?|flow ?diagrams?|workflows?|process (map|flow)|"
    r"org(ani[sz]ation)? ?charts?|organogram|hierarch(y|ies)|"
    r"(decision|family) tree|tree (diagram|chart|map|view)|mind ?maps?|venn|"
    r"time ?lines?|road ?maps?|gantt|swim ?lanes?|"
    # chart shapes show_chart cannot express
    r"sankey|funnels?|pyramids?|waterfalls?|treemaps?|sunbursts?|heat ?maps?|"
    r"scatter|bubble chart|radar chart|spider chart|doughnuts?|donuts?|"
    r"area chart|stacked|grouped bars?|histograms?|box ?plots?|bell curve|"
    r"gauges?|speedometer|multi[- ]?series|multiple series|dual axis|combo chart|"
    r"matrix|quadrant|"
    # hand-built visuals and interactive things
    r"infographics?|mock ?ups?|wireframes?|prototypes?|"
    r"calculators?|simulators?|simulations?|interactive|sliders?|toggles?|"
    r"animations?|animated|kanban|floor ?plans?|seating|"
    r"svg|illustrations?|illustrate|drawings?|draw|sketch|picture|graphic|"
    r"visuali[sz]e|visuali[sz]ation|visually"
    r")\b",
    re.IGNORECASE,
)


def needs_design_rules(text: str) -> bool:
    """
    True when the question asks for something only show_widget can draw, so
    WIDGET_DESIGN_PROMPT is worth its ~1.4k tokens.

    Pass the same routing text the schema router gets (tools.routing_text: the
    previous user turn plus this question), so a follow-up on a widget ("now
    add the polishing stage" after "draw the process flow") keeps the rules
    loaded instead of losing them mid-conversation.
    """
    return bool(text) and bool(_CUSTOM_VISUAL_RE.search(text))


def visual_prompt_for(text: str) -> str:
    """
    The design block to append AFTER the per-question schema, or "" when this
    question does not need it. Backends concatenate it dead last - see the
    placement note above.
    """
    return WIDGET_DESIGN_PROMPT if needs_design_rules(text) else ""
