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

# Above this row count a category chart is meaningless (a 1000-bar chart is
# noise) - the export then ships data only, no chart. Small top-N answers (the
# kind the chatbot draws a chart for) fall well under this.
CHART_MAX_ROWS = 50


def _to_number(value):
    """Coerce a cell to a float for plotting; non-numbers -> 0.0."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def pick_chart_columns(columns: list[str], rows: list[dict]) -> tuple[str, str] | None:
    """
    Auto-pick (label_col, value_col) for a chart: the first text column as the
    category labels and a numeric (non-ID) column as the bar heights. Returns
    None when the data isn't chartable (no text label, or no numeric measure).
    """
    if not columns or not rows:
        return None
    sample = rows[0]

    label_col = next(
        (c for c in columns if isinstance(sample.get(c), str)), None
    )
    # Prefer the LAST numeric non-ID column - usually the measure (total/amount).
    value_col = None
    for c in columns:
        v = sample.get(c)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and not c.lower().endswith("id"):
            value_col = c
    if not label_col or not value_col:
        return None
    return label_col, value_col


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
    from matplotlib.ticker import FuncFormatter

    xs = [str(row.get(x_col)) for row in rows]
    ys = [_to_number(row.get(y_col)) for row in rows]

    fig, ax = plt.subplots(figsize=(10, 6))
    brand = "#2a78d6"  # same blue as the Excel chart, for a consistent look

    if kind == "line":
        ax.plot(xs, ys, marker="o", color=brand, linewidth=2)
    elif kind == "pie":
        ax.pie(ys, labels=xs, autopct="%1.1f%%", startangle=90)
    else:  # default: bar
        bars = ax.bar(xs, ys, color=brand)
        # Value on top of each bar (thousands-formatted) - easy to read.
        ax.bar_label(bars, labels=[f"{v:,.0f}" for v in ys], padding=3, fontsize=8, color="#333333")

    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    if kind != "pie":
        ax.set_xlabel(x_col, fontsize=10)
        ax.set_ylabel(y_col, fontsize=10)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:,.0f}"))  # thousands
        ax.grid(axis="y", alpha=0.3, linewidth=0.6)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        plt.xticks(rotation=45, ha="right")

    plt.tight_layout()
    path = output_path(filename)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
