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

# Same shape as the entries in tools.TOOL_SPECS. Each backend converts this into
# its provider-specific tool format alongside the DB tools.
SHOW_WIDGET_TOOL_SPEC = {
    "name": "show_widget",
    "description": (
        "Render inline visual content (HTML or SVG) in the chat - charts, "
        "dashboards, calculators, diagrams, forms, interactive explainers. "
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


# Prepended to (merged into) the system prompt on every chat call. The CSS
# variables below are defined in frontend/src/SandboxedWidget.jsx (the iframe
# host); they auto-adapt to light and dark mode. Keep the rules verbatim - they
# prevent the broken/inconsistent output you'd otherwise get.
WIDGET_SYSTEM_PROMPT = """
You can render rich visual content inline using the show_widget tool. When a visual conveys
something text can't - data shape, structure, a process, an interactive tool - call show_widget
with an HTML or SVG fragment. Otherwise answer in prose. Put all explanation in your text
response; the widget contains ONLY the visual.

# When to call show_widget (important)
- If the user asks you to draw, plot, chart, graph, visualize, diagram, or render something,
  call show_widget with a real HTML/SVG fragment. Do NOT describe the visual in words.
- BE PROACTIVE with analytics: even when NOT explicitly asked, if a result compares categories
  (by colour, department, city, party), breaks something down, ranks a top-N, or trends over
  time, render a bar/line chart with show_widget alongside your written answer. A good rule:
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
