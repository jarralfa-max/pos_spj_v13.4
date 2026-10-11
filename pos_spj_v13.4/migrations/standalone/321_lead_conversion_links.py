"""321 — el prospecto recuerda a qué cliente y oportunidad se convirtió (2026-10-09).

Auditoría externa de Clientes/CRM (F16): la relación prospecto → cliente sólo
viajaba en el evento ``CRM_LEAD_CONVERTED``; el prospecto no la guardaba, la
oportunidad se creaba con un ``customer_id`` que nadie comparaba y, si fallaba,
reintentar no tenía de dónde retomar. Agrega ``leads.converted_customer_id`` y
``leads.converted_opportunity_id`` y completa el primero, para los prospectos ya
convertidos, desde el evento guardado en el outbox del CRM. Idempotente.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("spj.migrations.321")


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def run(conn) -> None:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='leads'"
                        ).fetchone():
        return
    columns = _columns(conn, "leads")
    for column in ("converted_customer_id", "converted_opportunity_id"):
        if column not in columns:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {column} TEXT")
    rellenados = 0
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='crm_outbox'"
                    ).fetchone():
        outbox_cols = _columns(conn, "crm_outbox")
        payload_col = "payload_json" if "payload_json" in outbox_cols else "payload"
        rows = conn.execute(
            f"SELECT {payload_col} FROM crm_outbox WHERE event_name='CRM_LEAD_CONVERTED'"
        ).fetchall()
        for (payload,) in rows:
            try:
                data = json.loads(payload or "{}")
            except ValueError:
                continue
            lead_id, customer_id = data.get("lead_id"), data.get("customer_id")
            if lead_id and customer_id:
                rellenados += conn.execute(
                    "UPDATE leads SET converted_customer_id=? WHERE id=?"
                    " AND converted_customer_id IS NULL", (customer_id, lead_id)).rowcount or 0
    conn.commit()
    logger.info("321: vínculos de conversión listos; %s prospectos completados.", rellenados)


up = run
