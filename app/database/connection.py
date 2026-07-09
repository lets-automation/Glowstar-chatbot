"""
connection.py
-------------
Creates the connection to the Aastha ERP SQL Server database.

SQLAlchemy (database toolkit) sits on top of pyodbc (the SQL Server
driver). We use Windows Authentication, so it logs in as the current
Windows user - no username/password needed, exactly like SSMS.
"""

import urllib.parse

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import settings


def _build_connection_url() -> str:
    """Build the SQLAlchemy connection URL for SQL Server (Windows auth)."""
    # Auth: SQL login (UID/PWD) if DB_USER is set, else Windows Authentication.
    if settings.DB_USER:
        auth = f"UID={settings.DB_USER};PWD={settings.DB_PASSWORD};"
    else:
        auth = "Trusted_Connection=yes;"

    # Raw ODBC connection string.
    #  - TrustServerCertificate=yes -> accept the self-signed cert (SSMS fix)
    odbc_str = (
        f"DRIVER={{{settings.DB_DRIVER}}};"
        f"SERVER={settings.DB_SERVER};"
        f"DATABASE={settings.DB_NAME};"
        f"{auth}"
        f"TrustServerCertificate=yes;"
    )
    # SQLAlchemy wants the ODBC string URL-encoded inside odbc_connect.
    return "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc_str)


# The "engine" is the shared, reusable gateway to the database.
#  - pool_pre_ping: quietly check a connection is alive before use (auto-recover
#    from a dropped connection instead of erroring).
#  - pool_size/max_overflow: bound concurrent connections so a burst of requests
#    can't exhaust the pool and hang; pool_timeout fails fast (10s) rather than
#    blocking forever when all connections are busy.
#  - pool_recycle: drop connections older than 30 min (avoids stale-socket
#    errors from server-side idle timeouts).
engine: Engine = create_engine(
    _build_connection_url(),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=10,
    pool_recycle=1800,
)


def get_engine() -> Engine:
    """Return the shared database engine for other modules to use."""
    return engine
