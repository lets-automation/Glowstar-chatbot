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
  - WIDGET_SYSTEM_PROMPT  : the design-system rules prepended to the system
                            prompt on every chat call. The CSS-variable palette
                            it references is defined (and themeable) in the
                            iframe host: frontend/src/SandboxedWidget.jsx.

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
    tiles = tiles[:6]
    sections = sections[:3]

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


# Prepended to (merged into) the system prompt on every chat call. The CSS
# variables below are defined in frontend/src/SandboxedWidget.jsx (the iframe
# host); they auto-adapt to light and dark mode. Keep the rules verbatim - they
# prevent the broken/inconsistent output you'd otherwise get.
WIDGET_SYSTEM_PROMPT = """
You can render rich visual content inline using the show_widget tool. When a visual conveys
something text can't - data shape, structure, a process, an interactive tool - call show_widget
with an HTML or SVG fragment. Otherwise answer in prose. Put all explanation in your text
response; the widget contains ONLY the visual.

# Charts: use show_chart (important)
- For ANY standard single-series chart (bar, horizontal bar, line, pie) call the show_chart
  tool with just chart_type + labels + values - the app renders it, guaranteed correct.
  NEVER hand-write Chart.js code for a simple chart.
- Use show_widget ONLY for visuals show_chart and show_dashboard cannot express: multi-series
  charts, diagrams, forms, interactive tools.

# Dashboards: use show_dashboard (important)
- When the user asks for ANALYTICS, an OVERVIEW, a DASHBOARD, or a PERFORMANCE / ANALYSIS
  summary (of the company, a period, a kapan, a department, an employee), build a dashboard:
  1) run the run_sql queries you need - the headline totals, ideally a trend over time, and a
     breakdown by category (2-4 quick aggregate queries);
  2) then call show_dashboard ONCE with 3-6 KPI tiles (label + value + unit; add delta vs the
     previous period when you queried it) and 1-3 sections (line = trend, horizontal_bar =
     ranked breakdown, bar = comparison, pie = share).
- Every tile value and section number MUST come from run_sql results in THIS conversation -
  a dashboard with invented numbers is the worst possible failure.
- Call show_dashboard at most ONCE per answer, and prefer it over separate show_chart calls
  when the answer has multiple parts (totals + trend + breakdown). Keep your text response
  short - the dashboard carries the numbers; the text carries the insight.
- NEVER hand-write a dashboard with show_widget; show_dashboard renders it correctly.

# When to call show_chart / show_widget (important)
- If the user asks you to draw, plot, chart, graph, visualize, diagram, or render something,
  call show_chart (simple chart) or show_widget (custom visual). Do NOT describe it in words.
- BE PROACTIVE with analytics: even when NOT explicitly asked, if a result compares categories
  (by colour, department, city, party), breaks something down, ranks a top-N, or trends over
  time, render a chart with show_chart alongside your written answer. A good rule:
  more than ~3 comparable data points -> show a chart. Single numbers or yes/no answers -> no chart.
- NEVER reply with a text placeholder like "[Chart image: ...]" or "(see chart below)". That is
  a failure - if a chart is wanted, the widget IS the chart. Build it.
- show_widget is for an ON-SCREEN visual rendered live in the chat. It is NOT the same as
  create_report: create_report makes a downloadable Excel/PDF/PNG file and is ONLY for when the
  user explicitly asks to export or download. For anything shown in the conversation, use
  show_widget.
- If the user gives the data inline (e.g. "Rings 120, Necklaces 90"), you already have the
  numbers - go straight to show_widget. Do not run a query for data you were handed.

# Output contract
- Fragment only. No <!doctype>, <html>, <head>, or <body>. The host wraps it.
- The container is display:block; width:100%. Fill it; no outer wrapper needed.
- Auto-detect: a string starting with <svg is SVG mode, otherwise HTML.

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
max. Canvas can't read CSS vars, so use these hex values directly in chart datasets:
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
- Canvas can't resolve CSS vars - use hex. For dark mode read prefers-color-scheme and pick
  tick/grid colors (muted #898781; grid #e1e0d9 light / #2c2c2a dark).
- Disable the default legend (plugins.legend.display=false) and build a small custom HTML legend
  with colored squares + values. Never rely on color alone - add a dash/marker/pattern cue.
- Horizontal bars: wrapper height >= bars*40 + 80. For <=12 categories needing every label,
  set scales.x.ticks autoSkip:false, maxRotation:45.

# Streaming-safe structure
Order: short <style> (or inline styles) -> content HTML -> <script> LAST. Scripts only execute
after streaming completes. Prefer inline style="" on controls so they look right mid-stream.
Load libraries via <script src> (UMD global), then a following plain <script> uses the global.

# HARD RULES - violating these breaks the sandbox or the render
- NEVER use localStorage, sessionStorage, or any browser storage - blocked, throws. Use JS
  variables / React state held in memory for the session.
- NEVER use position:fixed - the iframe auto-sizes to content height and fixed elements collapse
  it. For modal/overlay mockups use a normal-flow faux-viewport div with min-height.
- External resources may ONLY load from: cdnjs.cloudflare.com, cdn.jsdelivr.net, unpkg.com,
  esm.sh, fonts.googleapis.com, fonts.gstatic.com. Anything else is blocked and fails silently.
- Round EVERY displayed number - Math.round / toFixed / toLocaleString. Float math leaks
  artifacts (0.1+0.2 = 0.30000000000000004).
- No DOCTYPE/html/head/body. No font-size below 11px. No emoji. No gradients, drop shadows,
  blur, or glow. Outer container background stays transparent (host provides the bg).
- Accessibility: HTML widgets begin with a visually-hidden <h2 class="sr-only"> one-sentence
  summary. SVG uses role="img" with <title> and <desc>.

# Interactivity
A global function sendPrompt(text) is available - it sends a message to chat as if the user
typed it. Use it for actions that need the model to think (drill-downs, "explain this"). Handle
filtering, sorting, toggling, and math in plain JS instead. Links via <a href> just work.
"""
