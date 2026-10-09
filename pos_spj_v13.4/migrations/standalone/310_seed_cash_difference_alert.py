"""310 — aviso de «Diferencia en Corte Z» para los dueños.

POR QUÉ HACE FALTA (medido en la base viva el 2026-10-07)
---------------------------------------------------------
`cash_alert_rules` y sus destinatarios estaban vacíos y los destinatarios no
tenían escritor: el Corte Z detectaba un faltante y no avisaba a nadie. La
decisión del usuario (2026-10-07) es avisar las diferencias «en el sistema y
por WhatsApp».

QUÉ HACE
--------
* Regla vigente para `CASH_DIFFERENCE_DETECTED` (severidad Advertencia; canales
  en el sistema y WhatsApp), alcance de todo el sistema — sólo si no existe ya
  una regla para ese evento.
* Destinatarios en el sistema: los usuarios ACTIVOS con rol `system_owner`.

NO siembra teléfonos de WhatsApp: mandar mensajes a un número que nadie
capturó para esto no es un valor por omisión aceptable. Se agregan en
Caja → Configuración → Destinatarios.
"""

from __future__ import annotations

import json
import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.310")

_EVENTO = "CASH_DIFFERENCE_DETECTED"
_DESDE = "2026-01-01T00:00:00+00:00"


def run(conn) -> None:
    tablas = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"cash_alert_rules", "cash_in_app_recipients", "usuarios"} <= tablas:
        return
    if conn.execute("SELECT 1 FROM cash_alert_rules WHERE event_name=?", (_EVENTO,)).fetchone():
        logger.info("310: ya existe un aviso para %s; no se toca", _EVENTO)
        return
    regla = new_uuid()
    conn.execute(
        "INSERT INTO cash_alert_rules (id, event_name, severity, channels_json, scope_type,"
        " scope_id, active, effective_from, effective_to)"
        " VALUES (?, ?, 'WARNING', ?, 'SYSTEM', NULL, 1, ?, NULL)",
        (regla, _EVENTO, json.dumps(["IN_APP", "WHATSAPP"]), _DESDE))
    duenos = conn.execute(
        "SELECT id, COALESCE(NULLIF(trim(nombre),''), usuario) FROM usuarios"
        " WHERE rol='system_owner' AND activo=1 ORDER BY 2").fetchall()
    for user_id, nombre in duenos:
        conn.execute(
            "INSERT INTO cash_in_app_recipients (id, alert_rule_id, user_id, display_name, active)"
            " VALUES (?, ?, ?, ?, 1)", (new_uuid(), regla, user_id, nombre))
    conn.commit()
    logger.info("310: aviso de diferencias creado para %d dueño(s)", len(duenos))


up = run
