"""
excel.py
--------
Turn query results into an Excel (.xlsx) file using openpyxl.

Input shape (same as the query runner returns):
  columns: ["Shape", "Cnt", ...]
  rows:    [ {"Shape": "ROUND", "Cnt": 123}, ... ]
"""

from openpyxl import Workbook
from openpyxl.styles import Font

from app.artifacts import output_path


def to_excel(columns: list[str], rows: list[dict], filename: str = "report.xlsx") -> str:
    """Write columns + rows to an .xlsx file. Returns the file path."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    # Header row (bold).
    ws.append(columns)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    # Data rows, in column order.
    for row in rows:
        ws.append([row.get(col) for col in columns])

    # Auto-ish column widths for readability.
    for i, col in enumerate(columns, start=1):
        max_len = max([len(str(col))] + [len(str(r.get(col, ""))) for r in rows])
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(
            max_len + 2, 50
        )

    path = output_path(filename)
    wb.save(path)
    return path
