"""Esquema del contexto de Calidad: inspecciones y su outbox.

Una inspección por sujeto (hoy, un output de producción). Guarda quién produjo
para poder impedir que esa misma persona decida, y la decisión con su autor.
"""

from __future__ import annotations

INSPECTION_STATUSES = "'PENDING','RELEASED','BLOCKED','REWORK_REQUIRED','CONDEMNED'"

QUALITY_TABLES: tuple[str, ...] = ("quality_inspections", "quality_outbox")

_DDL = (
    f"""
    CREATE TABLE IF NOT EXISTS quality_inspections (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        source_module TEXT NOT NULL,
        source_document_id TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        lot_id TEXT,
        branch_id TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        produced_by_user_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ({INSPECTION_STATUSES})),
        decided_by_user_id TEXT,
        decision_operation_id TEXT UNIQUE,
        reason TEXT,
        requested_at TEXT NOT NULL,
        decided_at TEXT,
        CHECK (decided_by_user_id IS NULL OR decided_by_user_id <> produced_by_user_id),
        UNIQUE (subject_type, subject_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quality_outbox (
        id TEXT NOT NULL PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DISPATCHED')),
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_quality_inspections_status"
    " ON quality_inspections(status, branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_quality_outbox_status ON quality_outbox(status, created_at)",
)


def create_quality_schema(conn) -> None:
    """Idempotente. La llama la migración 273."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_quality_schema(conn) -> list[str]:
    dropped = []
    for table in reversed(QUALITY_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
