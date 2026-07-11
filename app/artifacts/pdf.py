"""
pdf.py
------
Turn query results into a formatted PDF table using ReportLab.

A downloaded report must be the COMPLETE detail listing (the client's ERP
prints every row), so we render ALL rows the export gives us - ReportLab
paginates the table across pages automatically. A very high safety ceiling
(MAX_PDF_ROWS) only guards against a pathological full-table dump; realistic
reports (a kapan's packets, a month's production) are never truncated.

ROBUSTNESS (this app's data is real ERP text - Gujarati/Hindi names, legacy
free-text, very wide SELECT * results):
  - A Unicode TrueType font (DejaVuSans, bundled with matplotlib) is registered
    and used everywhere. ReportLab's built-in Helvetica is Latin-1 only and
    raises UnicodeEncodeError on any non-Latin-1 character (e.g. Gujarati); a
    registered TTF uses the font's own Unicode map, so non-Latin text never
    crashes the build (glyphs the font lacks render as blanks, not an error).
  - Every cell is a wrapping Paragraph with computed column widths, so a wide
    result set wraps to fit the page instead of raising a LayoutError.
"""

import os
import uuid

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.artifacts import output_path
from app.artifacts.charts import CHART_MAX_ROWS, pick_chart_columns, to_chart

# Safety ceiling only - a report renders ALL its rows (paginated). This guards
# against a pathological full-table dump (e.g. all 164k packets), NOT normal
# reports. A per-kapan packet report (<=842 rows) or a month's production is
# always well under this and prints in full.
MAX_PDF_ROWS = 5000
# Beyond this, a landscape table's columns get too thin to read; note the rest.
MAX_PDF_COLS = 15


def _register_unicode_font() -> str:
    """
    Register DejaVuSans (ships with matplotlib, always installed here) so PDFs
    can render non-Latin-1 text without crashing. Returns the font name to use,
    falling back to Helvetica only if the TTF genuinely can't be found.
    """
    name = "DejaVuSans"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    try:
        import matplotlib

        ttf = os.path.join(
            os.path.dirname(matplotlib.__file__),
            "mpl-data", "fonts", "ttf", "DejaVuSans.ttf",
        )
        pdfmetrics.registerFont(TTFont(name, ttf))
        return name
    except Exception:
        return "Helvetica"  # last resort (Latin-1 only; may still fail on Gujarati)


_FONT = _register_unicode_font()


def to_pdf(
    columns: list[str],
    rows: list[dict],
    filename: str = "report.pdf",
    title: str = "Report",
) -> str:
    """Write columns + rows to a PDF table. Returns the file path."""
    path = output_path(filename)
    doc = SimpleDocTemplate(path, pagesize=landscape(A4))
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("GsTitle", parent=styles["Title"], fontName=_FONT)
    note_style = ParagraphStyle("GsNote", parent=styles["Italic"], fontName=_FONT)
    heading_style = ParagraphStyle("GsHeading", parent=styles["Heading2"], fontName=_FONT)
    # Cell/header paragraph styles: small, wrapping, Unicode font.
    cell_style = ParagraphStyle(
        "GsCell", fontName=_FONT, fontSize=7, leading=9, alignment=TA_LEFT, wordWrap="CJK"
    )
    head_style = ParagraphStyle(
        "GsHead", fontName=_FONT, fontSize=7, leading=9, textColor=colors.white, wordWrap="CJK"
    )

    elements = [Paragraph(_esc(title), title_style), Spacer(1, 12)]

    # Cap columns so the table stays legible; note any that were dropped.
    shown_cols = columns[:MAX_PDF_COLS]
    dropped_cols = len(columns) - len(shown_cols)

    shown = rows[:MAX_PDF_ROWS]
    # Wrap every cell in a Paragraph so long text wraps within its column instead
    # of overflowing the page (which would raise a LayoutError).
    header_row = [Paragraph(_esc(str(c)), head_style) for c in shown_cols]
    table_data = [header_row] + [
        [Paragraph(_esc(_fmt(row.get(col, ""))), cell_style) for col in shown_cols]
        for row in shown
    ]

    # Even column widths across the usable page width.
    usable_width = landscape(A4)[0] - doc.leftMargin - doc.rightMargin
    col_width = usable_width / max(1, len(shown_cols))

    table = Table(table_data, repeatRows=1, colWidths=[col_width] * len(shown_cols))
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(table)

    notes = []
    if len(rows) > MAX_PDF_ROWS:
        notes.append(f"{len(rows) - MAX_PDF_ROWS} more rows omitted (showing first {MAX_PDF_ROWS}) — use the Excel export for the complete list")
    if dropped_cols > 0:
        notes.append(f"{dropped_cols} more columns omitted (showing first {MAX_PDF_COLS}) — use the Excel export for all columns")
    if notes:
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("... " + "; ".join(notes) + ".", note_style))

    # Chart at the end (only when the data is chartable and not too large).
    picked = pick_chart_columns(columns, rows) if 1 < len(rows) <= CHART_MAX_ROWS else None
    if picked:
        label_col, value_col = picked
        try:
            img_path = to_chart(
                rows,
                label_col,
                value_col,
                # Unique temp name: a fixed shared filename let two concurrent
                # exports embed each other's chart image.
                filename=f"export_chart-{uuid.uuid4().hex}.png",
                kind="bar",
                title=f"{value_col} by {label_col}",
            )
            elements.append(Spacer(1, 18))
            elements.append(Paragraph("Chart", heading_style))
            elements.append(Spacer(1, 8))
            # A4 landscape usable width ~ 720pt; keep the 10:6 aspect of to_chart.
            elements.append(Image(img_path, width=560, height=336))
        except Exception:
            pass  # a chart failure must never break the data export

    doc.build(elements)
    return path


def _fmt(value) -> str:
    """None -> empty string; everything else -> str."""
    return "" if value is None else str(value)


def _fmt_num(value) -> str:
    """Thousands-separated number for display; strings/None pass through."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def _report_table_style() -> "TableStyle":
    """The shared header/grid/zebra style for every report table."""
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
    )


def dashboard_to_pdf(
    dashboard: dict,
    filename: str = "dashboard.pdf",
    title: str = "",
) -> str:
    """
    Render a FULL analytics dashboard to PDF: the headline KPI figures, then
    EVERY chart section (as a chart image) followed by its own data table. This
    is the complete detail behind the on-screen dashboard - not a single summary
    table. `dashboard` is the show_dashboard payload {title, subtitle, tiles[],
    sections[]}. Returns the file path.
    """
    d_title = str(dashboard.get("title") or title or "Analytics Report")
    subtitle = str(dashboard.get("subtitle") or "")
    tiles = (dashboard.get("tiles") or [])[:12]
    sections = (dashboard.get("sections") or [])[:6]

    path = output_path(filename)
    doc = SimpleDocTemplate(path, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("GsTitle", parent=styles["Title"], fontName=_FONT)
    sub_style = ParagraphStyle(
        "GsSub", parent=styles["Normal"], fontName=_FONT, fontSize=11,
        textColor=colors.HexColor("#555555"),
    )
    heading_style = ParagraphStyle("GsHeading", parent=styles["Heading2"], fontName=_FONT)
    cell_style = ParagraphStyle(
        "GsCell", fontName=_FONT, fontSize=8, leading=10, alignment=TA_LEFT, wordWrap="CJK"
    )
    head_style = ParagraphStyle(
        "GsHead", fontName=_FONT, fontSize=8, leading=10, textColor=colors.white, wordWrap="CJK"
    )

    usable_width = landscape(A4)[0] - doc.leftMargin - doc.rightMargin
    elements = [Paragraph(_esc(d_title), title_style)]
    if subtitle:
        elements += [Spacer(1, 4), Paragraph(_esc(subtitle), sub_style)]
    elements.append(Spacer(1, 14))

    # --- KPI tiles -> "Key figures" table ---
    if tiles:
        elements.append(Paragraph("Key figures", heading_style))
        elements.append(Spacer(1, 6))
        kpi_rows = [[Paragraph(_esc(h), head_style) for h in ("Metric", "Value", "Change")]]
        for t in tiles:
            unit = str(t.get("unit") or "")
            value = f"{_fmt_num(t.get('value'))}{(' ' + unit) if unit else ''}"
            kpi_rows.append([
                Paragraph(_esc(str(t.get("label", ""))), cell_style),
                Paragraph(_esc(value), cell_style),
                Paragraph(_esc(str(t.get("delta") or "")), cell_style),
            ])
        kpi_tbl = Table(
            kpi_rows, repeatRows=1,
            colWidths=[usable_width * 0.5, usable_width * 0.3, usable_width * 0.2],
        )
        kpi_tbl.setStyle(_report_table_style())
        elements.append(kpi_tbl)
        elements.append(Spacer(1, 18))

    # --- Each chart section: heading + chart image + its data table ---
    kind_map = {"horizontal_bar": "bar", "bar": "bar", "line": "line", "pie": "pie"}
    for i, s in enumerate(sections):
        s_title = str(s.get("title") or f"Section {i + 1}")
        labels = [str(x) for x in (s.get("labels") or [])][:500]
        values = list(s.get("values") or [])[:500]
        series = str(s.get("series_label") or "Value")
        elements.append(Paragraph(_esc(s_title), heading_style))
        elements.append(Spacer(1, 6))
        if labels and values and len(labels) == len(values):
            try:
                rows_for_chart = [{"label": l, "value": v} for l, v in zip(labels, values)]
                kind = kind_map.get(str(s.get("type")), "bar")
                img = to_chart(
                    rows_for_chart, "label", "value",
                    # Unique temp name (see export_chart above - concurrency).
                    filename=f"dash_sec_{i}-{uuid.uuid4().hex}.png", kind=kind, title=s_title,
                )
                elements.append(Image(img, width=560, height=336))
                elements.append(Spacer(1, 8))
            except Exception:
                pass  # a chart failure must never break the data export
            data_rows = [[Paragraph(_esc("Category"), head_style), Paragraph(_esc(series), head_style)]]
            for l, v in zip(labels, values):
                data_rows.append([Paragraph(_esc(l), cell_style), Paragraph(_esc(_fmt_num(v)), cell_style)])
            sec_tbl = Table(
                data_rows, repeatRows=1,
                colWidths=[usable_width * 0.6, usable_width * 0.4],
            )
            sec_tbl.setStyle(_report_table_style())
            elements.append(sec_tbl)
        elements.append(Spacer(1, 20))

    doc.build(elements)
    return path


def _esc(text: str) -> str:
    """Escape the XML metacharacters ReportLab's Paragraph parser would choke on."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
