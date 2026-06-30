"""
Artifacts package - Phase 6.
Turns query results into downloadable files: Excel, PDF, and charts.
All files are written to the project's "outputs" folder.
"""

import os

# outputs/ folder at the project root.
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "outputs"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def output_path(filename: str) -> str:
    """Return the full path inside the outputs/ folder for a given filename."""
    return os.path.join(OUTPUT_DIR, filename)
