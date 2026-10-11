"""322 — SLA: pausas medidas y resultado de cumplimiento (2026-10-09).

Auditoría externa de Clientes/CRM (F11): pausar sólo cambiaba un indicador; el
vencimiento quedaba fijo y una resolución tardía se mostraba «Cumplido». Agrega a
``sla_instances``: ``paused_at`` y ``paused_seconds`` (la espera se descuenta al
reanudar) y ``first_response_outcome``/``resolution_outcome`` (MET/MISSED).

Para las SLA ya resueltas calcula el resultado comparando ``resolved_at`` /
``first_response_at`` con su vencimiento; una pausa abierta antes de esta
migración no tiene inicio conocido y se reanuda sin recorrer el plazo.
Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.322")

_COLUMNS = (("paused_at", "TEXT"), ("paused_seconds", "INTEGER NOT NULL DEFAULT 0"),
            ("first_response_outcome", "TEXT"), ("resolution_outcome", "TEXT"))


def run(conn) -> None:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                        " AND name='sla_instances'").fetchone():
        return
    existing = {row[1] for row in conn.execute("PRAGMA table_info(sla_instances)")}
    for name, ddl in _COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE sla_instances ADD COLUMN {name} {ddl}")
    conn.execute(
        "UPDATE sla_instances SET resolution_outcome = CASE WHEN resolved_at <= resolution_due_at"
        " THEN 'MET' ELSE 'MISSED' END WHERE resolved_at IS NOT NULL"
        " AND resolution_outcome IS NULL")
    conn.execute(
        "UPDATE sla_instances SET first_response_outcome = CASE"
        " WHEN first_response_at <= first_response_due_at THEN 'MET' ELSE 'MISSED' END"
        " WHERE first_response_at IS NOT NULL AND first_response_outcome IS NULL")
    conn.commit()
    logger.info("322: SLA con pausas medidas y resultado de cumplimiento.")


up = run
