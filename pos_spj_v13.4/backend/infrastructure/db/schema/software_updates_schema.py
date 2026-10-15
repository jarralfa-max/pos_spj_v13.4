"""DDL — software distribution: per-station version inventory and the update
event trail (checks, downloads, installs, rollbacks, channel changes).

`software_station_settings` is the station's row: installed version, schema,
channel (stable/pilot), maintenance window. The sync engine can ship it to the
central office, which is how versions are inventoried per station and branch.

`software_update_events` is append-only. Install outcomes are written by the
desktop when it starts after the external updater finished (the updater
journals to a file because a database restore would erase a row written
before it).

Only migration 338 may call `create_software_updates_schema`.
"""
from __future__ import annotations

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS software_station_settings (
        id TEXT NOT NULL PRIMARY KEY,
        workstation_key TEXT NOT NULL UNIQUE,
        branch_id TEXT,
        channel TEXT NOT NULL DEFAULT 'stable' CHECK (channel IN ('stable', 'pilot')),
        maintenance_window TEXT,
        installed_version TEXT,
        schema_version INTEGER,
        install_profile TEXT,
        enabled_capabilities TEXT,
        last_seen_at TEXT,
        last_check_at TEXT,
        last_check_result TEXT,
        updated_by TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS software_update_events (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL,
        job_id TEXT,
        workstation_key TEXT NOT NULL,
        branch_id TEXT,
        event_type TEXT NOT NULL,
        from_version TEXT,
        to_version TEXT,
        channel TEXT,
        detail TEXT,
        actor_user_id TEXT,
        occurred_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_software_update_events_station "
    "ON software_update_events (workstation_key, occurred_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_software_update_events_job_outcome "
    "ON software_update_events (job_id, event_type) WHERE job_id IS NOT NULL",
)


def create_software_updates_schema(conn) -> None:
    for statement in _DDL:
        conn.execute(statement)
