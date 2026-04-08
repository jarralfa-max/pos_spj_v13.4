
# migrations/standalone/051_fix_kpi_snapshots.py
# ── Fix: kpi_snapshots table ─────────────────────────────────────────────────
#
# Migration 032 contained a SQL syntax error in _create_kpi_snapshots:
#   "CREATE TABLE IF NOT EXISTS kpi_snapshots (..."  ← invalid SQL
#
# That caused 032 to DROP the table (which existed from 023) but fail to
# recreate it, leaving kpi_snapshots absent in any DB where 032 already ran.
#
# This migration creates kpi_snapshots with the canonical schema that
# report_engine.py expects (branch_id + snapshot_date).
# Idempotent — safe to run on any installation.

import logging, sqlite3

logger = logging.getLogger("spj.migrations.051")


def run(conn: sqlite3.Connection) -> None:
    # Check if the existing kpi_snapshots has the correct schema.
    # If it's missing 'snapshot_date' (the canonical column), drop and recreate.
    existing_cols = set()
    try:
        existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(kpi_snapshots)").fetchall()}
    except Exception:
        pass

    if existing_cols and "snapshot_date" not in existing_cols:
        # Wrong schema (e.g. the m000/024 version with date_from/date_to) — recreate
        conn.execute("DROP TABLE IF EXISTS kpi_snapshots")
        try:
            conn.commit()
        except Exception:
            pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS kpi_snapshots (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id        INTEGER NOT NULL,
            snapshot_date    DATE    NOT NULL,
            total_revenue    REAL    NOT NULL DEFAULT 0,
            total_cost       REAL    NOT NULL DEFAULT 0,
            gross_margin     REAL    NOT NULL DEFAULT 0,
            gross_margin_pct REAL    NOT NULL DEFAULT 0,
            ticket_count     INTEGER NOT NULL DEFAULT 0,
            avg_ticket       REAL    NOT NULL DEFAULT 0,
            active_clients   INTEGER NOT NULL DEFAULT 0,
            new_clients      INTEGER NOT NULL DEFAULT 0,
            points_issued    INTEGER NOT NULL DEFAULT 0,
            inventory_value  REAL    NOT NULL DEFAULT 0,
            computed_at      DATETIME NOT NULL DEFAULT (datetime('now')),
            UNIQUE (branch_id, snapshot_date)
        )
    """)

    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_kpi_snap_branch ON kpi_snapshots(branch_id)",
        "CREATE INDEX IF NOT EXISTS idx_kpi_snap_date   ON kpi_snapshots(snapshot_date)",
        "CREATE INDEX IF NOT EXISTS idx_kpi_snap_bd     ON kpi_snapshots(branch_id, snapshot_date DESC)",
    ]:
        try:
            conn.execute(idx_sql)
        except Exception:
            pass

    try:
        conn.commit()
    except Exception:
        pass

    logger.info("Migration 051: kpi_snapshots creada/verificada.")
