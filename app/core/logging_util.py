"""
logging_util.py
---------------
Light observability for the agent. Records each question, the SQL the
agent ran, how many rows came back, and any error - to both the console
and a logfile (logs/agent.log).

This makes accuracy problems debuggable: when an answer looks wrong, you
can open the log and see exactly which SQL produced it.
"""

import logging
import os

# Put logs in a "logs" folder next to the project root.
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "agent.log")

# Configure one shared logger named "aastha".
logger = logging.getLogger("aastha")
if not logger.handlers:  # avoid adding handlers twice on re-import
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)


def log_interaction(
    question: str,
    sql_used: list[str],
    rows_returned: int,
    error: str = "",
) -> None:
    """Record one agent interaction (question + SQL + outcome)."""
    logger.info("Q: %s", question)
    for sql in sql_used:
        logger.info("   SQL: %s", sql)
    if error:
        logger.error("   ERROR: %s", error)
    else:
        logger.info("   rows_returned: %s", rows_returned)
