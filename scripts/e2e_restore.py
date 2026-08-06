"""
e2e_restore.py
--------------
Restore the client's AasthaErp .bak into the bundled `db` container, then create
the read-only login the backend uses.

    docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d db
    python -m scripts.e2e_restore

WHY A SCRIPT AND NOT A README SNIPPET
-------------------------------------
The snippet in docker-compose.yml hardcodes `MOVE 'AasthaErp'` / `'AasthaErp_log'`.
Those are NOT this backup's logical file names - it was taken from a database
whose files are called `JogiErp` / `JogiErp_log` (the ERP was renamed at some
point, and a rename does not touch logical file names). Running the documented
command therefore fails with "Logical file 'AasthaErp' is not part of database".

So this reads the names out of the backup with RESTORE FILELISTONLY instead of
assuming them, which also means it keeps working when the client sends the next
backup with different names again.

It connects from the HOST to the container's published 127.0.0.1:1433 using
pyodbc (already a dependency) rather than shelling into the container for
sqlcmd - one less layer of shell quoting, and real error objects.

Safe to re-run: the restore uses WITH REPLACE, and the login/user creation is
idempotent.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Where the .bak is visible INSIDE the db container (see docker-compose.e2e.yml).
CONTAINER_BACKUP_DIR = "/var/opt/mssql/backup"
# Where the restored data files go inside the container (the mssql_data volume).
CONTAINER_DATA_DIR = "/var/opt/mssql/data"

_DEF_HOST = "127.0.0.1,1433"


def _connect(server: str, password: str, database: str = "master", timeout: int = 30):
    import pyodbc

    for driver in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
        try:
            return pyodbc.connect(
                f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                f"UID=sa;PWD={password};TrustServerCertificate=yes;",
                timeout=timeout,
                autocommit=True,   # RESTORE cannot run inside a transaction
            )
        except pyodbc.Error as exc:
            last = exc
    raise SystemExit(
        f"Could not connect to {server} as sa.\n"
        f"  Is the db container up?  docker compose -f docker-compose.yml "
        f"-f docker-compose.e2e.yml ps db\n"
        f"  Last driver error: {last}"
    )


def _wait_for_sql(server: str, password: str, minutes: int = 5):
    """SQL Server takes ~20-40s to accept connections on first boot."""
    deadline = time.monotonic() + minutes * 60
    attempt = 0
    while True:
        attempt += 1
        try:
            conn = _connect(server, password, timeout=5)
            print(f"  connected (attempt {attempt})")
            return conn
        except SystemExit:
            if time.monotonic() > deadline:
                raise
            print(f"  waiting for SQL Server... (attempt {attempt})")
            time.sleep(5)


def _find_backup(backup_dir: Path, explicit: str | None) -> str:
    """Return the .bak FILENAME to restore (as seen inside the container)."""
    if explicit:
        return explicit
    if not backup_dir.is_dir():
        raise SystemExit(
            f"Backup folder not found: {backup_dir}\n"
            "Set BACKUP_DIR in .env to the folder holding your .bak, e.g.\n"
            "  BACKUP_DIR=C:/Program Files/Microsoft SQL Server/"
            "MSSQL17.SQLEXPRESS/MSSQL/Backup"
        )
    baks = sorted(backup_dir.glob("*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not baks:
        raise SystemExit(f"No .bak file in {backup_dir}")
    if len(baks) > 1:
        print(f"  {len(baks)} backups found; using the newest: {baks[0].name}")
    return baks[0].name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--server", default=os.getenv("E2E_DB_HOST", _DEF_HOST))
    ap.add_argument("--database", default=os.getenv("DB_NAME", "AasthaErp_new"))
    ap.add_argument("--bak", default=None, help="backup FILENAME (default: newest in BACKUP_DIR)")
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv()
    sa_password = os.getenv("DB_SA_PASSWORD", "")
    ro_password = os.getenv("DB_RO_PASSWORD", "")
    if not sa_password:
        raise SystemExit("DB_SA_PASSWORD is not set in .env")
    if not ro_password:
        raise SystemExit("DB_RO_PASSWORD is not set in .env (the backend logs in with it)")

    backup_dir = Path(os.getenv("BACKUP_DIR", "./db_backup"))
    bak_name = _find_backup(backup_dir, args.bak)
    bak_path = f"{CONTAINER_BACKUP_DIR}/{bak_name}"

    print(f"Restoring {bak_name} -> [{args.database}] on {args.server}")
    print("1. connecting")
    conn = _wait_for_sql(args.server, sa_password)
    cur = conn.cursor()

    # --- 2. read the backup's REAL logical file names -----------------------
    print("2. reading the backup header")
    cur.execute(f"RESTORE FILELISTONLY FROM DISK = N'{bak_path}'")
    cols = [d[0] for d in cur.description]
    files = [dict(zip(cols, r)) for r in cur.fetchall()]
    if not files:
        raise SystemExit(f"RESTORE FILELISTONLY returned nothing for {bak_path}")

    moves, total_gb = [], 0.0
    for f in files:
        logical, ftype = f["LogicalName"], f["Type"].upper()
        ext = "ldf" if ftype == "L" else "mdf"
        # Name the physical files after the TARGET database, not the logical
        # name, so two restores of differently-named backups can coexist.
        suffix = "_log" if ftype == "L" else ""
        physical = f"{CONTAINER_DATA_DIR}/{args.database}{suffix}.{ext}"
        moves.append(f"MOVE N'{logical}' TO N'{physical}'")
        gb = float(f["Size"]) / (1024 ** 3)
        total_gb += gb
        print(f"   {logical:<22} {ftype}  {gb:6.2f} GB -> {physical}")
    print(f"   {'TOTAL':<22}    {total_gb:6.2f} GB")

    # --- 3. restore ---------------------------------------------------------
    print(f"3. restoring (this takes several minutes for {total_gb:.1f} GB)")
    sql = (
        f"RESTORE DATABASE [{args.database}] FROM DISK = N'{bak_path}' WITH "
        + ", ".join(moves)
        + ", REPLACE, RECOVERY, STATS = 10"
    )
    t0 = time.monotonic()
    cur.execute(sql)
    # Drain the progress result sets STATS emits, or the restore looks hung.
    while cur.nextset():
        pass
    print(f"   restored in {time.monotonic() - t0:.0f}s")

    # --- 4. the read-only login the backend uses ----------------------------
    # Least privilege on purpose: the agent is a READ-ONLY analyst. sql_guard
    # already refuses non-SELECT text, but a database-enforced db_datareader is
    # what makes that guarantee real rather than best-effort.
    print(f"4. creating the read-only login glowstar_ro")
    cur.execute(
        f"""
        IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'glowstar_ro')
            CREATE LOGIN [glowstar_ro] WITH PASSWORD = N'{ro_password}',
                CHECK_POLICY = OFF, DEFAULT_DATABASE = [{args.database}];
        ELSE
            ALTER LOGIN [glowstar_ro] WITH PASSWORD = N'{ro_password}';
        """
    )
    cur.execute(
        f"""
        USE [{args.database}];
        IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'glowstar_ro')
            CREATE USER [glowstar_ro] FOR LOGIN [glowstar_ro];
        ALTER ROLE [db_datareader] ADD MEMBER [glowstar_ro];
        DENY INSERT, UPDATE, DELETE, ALTER, EXECUTE TO [glowstar_ro];
        """
    )

    # --- 5. prove it ---------------------------------------------------------
    # Connect straight to the restored database rather than prefixing "USE [x];".
    # A batch starting with USE returns that statement's (empty) result set
    # FIRST, so fetchval() raises "No results. Previous SQL was not a query."
    # before ever reaching the SELECT.
    print("5. verifying")
    conn.close()
    check = _connect(args.server, sa_password, args.database)
    ccur = check.cursor()
    tables = ccur.execute(
        "SELECT COUNT(*) FROM sys.tables WHERE name LIKE 'tbl%'"
    ).fetchval()
    packets = ccur.execute("SELECT COUNT(*) FROM tblPacket").fetchval()
    print(f"   business tables: {tables:,}")
    print(f"   tblPacket rows : {packets:,}")
    check.close()

    # And prove the READ-ONLY login actually works - that is what the backend
    # uses, so a broken grant must fail here, not at the first user question.
    import pyodbc

    ro_conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={args.server};"
        f"DATABASE={args.database};UID=glowstar_ro;PWD={ro_password};"
        "TrustServerCertificate=yes;",
        timeout=15,
    )
    rcur = ro_conn.cursor()
    rcur.execute("SELECT TOP 1 KapanName FROM tblKapan")
    print(f"   glowstar_ro can SELECT: yes")
    try:
        rcur.execute("CREATE TABLE dbo._e2e_write_probe (x int)")
        print("   WARNING: glowstar_ro was able to WRITE - the DENY did not apply")
    except pyodbc.Error:
        print("   glowstar_ro is read-only: writes rejected")
    ro_conn.close()

    print("\nDone. Bring up the rest of the stack:")
    print("  docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build")
    print("  python -m scripts.e2e_check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
