"""317 — entrega de los recordatorios del CRM (``crm_reminders.delivered_at``).

POR QUÉ HACE FALTA (medido en una copia de la base viva el 2026-10-09)
-------------------------------------------------------------------
Clientes y CRM permite programar recordatorios sobre actividades y tareas,
pero nada los entregaba: ``crm_reminders`` se escribía y nadie la leía. La
campana de la barra superior tampoco tenía fuente.

CRM-43 agrega el ciclo de fondo (``run_crm_background_cycle``) que, al llegar
la hora, deja el recordatorio en la bandeja personal (``notification_inbox``)
del destinatario. ``delivered_at`` marca el recordatorio como entregado para
que una segunda pasada no lo repita.

Idempotente: sólo agrega la columna si falta.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.317")


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def run(conn) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='crm_reminders'").fetchone()
    if not exists:
        logger.info("317: crm_reminders no existe todavía; el esquema CRM ya la crea con la columna.")
        return
    if "delivered_at" not in _columns(conn, "crm_reminders"):
        conn.execute("ALTER TABLE crm_reminders ADD COLUMN delivered_at TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_crm_reminders_pending"
        " ON crm_reminders(remind_at) WHERE delivered_at IS NULL")
    logger.info("317: crm_reminders.delivered_at listo.")
