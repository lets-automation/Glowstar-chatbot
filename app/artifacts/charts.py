"""
charts.py
---------
Turn query results into a chart image (.png) using matplotlib.

We force the non-interactive "Agg" backend so this works on a server
with no display.
"""

import matplotlib

matplotlib.use("Agg")  # headless - no GUI window
import matplotlib.pyplot as plt  # noqa: E402

from app.artifacts import output_path  # noqa: E402


def to_chart(
    rows: list[dict],
    x_col: str,
    y_col: str,
    filename: str = "chart.png",
    kind: str = "bar",
    title: str = "Chart",
) -> str:
    """
    Build a chart from rows.
      x_col / y_col : which columns to plot
      kind          : "bar", "line", or "pie"
    Returns the image file path.
    """
    xs = [str(row.get(x_col)) for row in rows]
    ys = [row.get(y_col) for row in rows]

    fig, ax = plt.subplots(figsize=(10, 6))

    if kind == "line":
        ax.plot(xs, ys, marker="o")
    elif kind == "pie":
        ax.pie(ys, labels=xs, autopct="%1.1f%%")
    else:  # default: bar
        ax.bar(xs, ys, color="#2c3e50")

    ax.set_title(title)
    if kind != "pie":
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        plt.xticks(rotation=45, ha="right")

    plt.tight_layout()
    path = output_path(filename)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
