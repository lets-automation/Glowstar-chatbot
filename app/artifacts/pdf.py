"""
pdf.py
------
Turn query results into a formatted PDF table using ReportLab.

PDFs are meant for reading, so we cap the number of rows shown (a 1000-row
PDF is unreadable). If there are more, we note how many were omitted.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.artifacts import output_path

# Max rows to render in a PDF (readability).
MAX_PDF_ROWS = 100


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

    elements = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

    shown = rows[:MAX_PDF_ROWS]
    table_data = [columns] + [
        [str(row.get(col, "")) for col in columns] for row in shown
    ]

    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(table)

    if len(rows) > MAX_PDF_ROWS:
        elements.append(Spacer(1, 10))
        elements.append(
            Paragraph(
                f"... {len(rows) - MAX_PDF_ROWS} more rows omitted "
                f"(showing first {MAX_PDF_ROWS}).",
                styles["Italic"],
            )
        )

    doc.build(elements)
    return path
