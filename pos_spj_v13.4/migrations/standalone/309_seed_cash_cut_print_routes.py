"""309 — los Cortes X y Z se imprimen en la impresora del ticket de venta.

POR QUÉ HACE FALTA (medido en la base viva el 2026-10-07)
---------------------------------------------------------
Caja imprime ahora por Document Output (rutas «Corte X» / «Corte Z», igual que
Ventas imprime por «Ticket de venta»). La base real tiene UNA impresora
(PRN-01) y UNA ruta, la del ticket de venta: sin esta migración el primer
Corte Z diría «No hay impresora asignada a los cortes de caja».

QUÉ HACE
--------
Por cada ruta ACTIVA de `SALE_TICKET`, crea la misma ruta para `X_REPORT` y
`Z_REPORT` (misma impresora, respaldo, sucursal y estación; sin módulo, porque
Caja no acota por módulo) — SÓLO si ese alcance no tiene ya una ruta de corte.
Lo que se asigne después en Configuración → Dispositivos manda.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid

_CORTES = ("X_REPORT", "Z_REPORT")


def run(conn) -> None:
    if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='print_routes'"
    ).fetchone() is None:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tickets = conn.execute(
        """SELECT primary_device_id, fallback_device_ids_json, branch_id, workstation_id
        FROM print_routes WHERE document_type='SALE_TICKET' AND active=1
        ORDER BY created_at, id""").fetchall()
    for device_id, fallbacks, branch_id, workstation_id in tickets:
        for document_type in _CORTES:
            existe = conn.execute(
                """SELECT 1 FROM print_routes WHERE document_type=?
                AND COALESCE(branch_id,'')=COALESCE(?,'')
                AND COALESCE(workstation_id,'')=COALESCE(?,'')""",
                (document_type, branch_id, workstation_id)).fetchone()
            if existe:
                continue
            conn.execute(
                """INSERT INTO print_routes
                (id, document_type, primary_device_id, fallback_device_ids_json,
                 branch_id, workstation_id, module, channel, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 1, ?, ?)""",
                (new_uuid(), document_type, device_id, fallbacks or "[]",
                 branch_id, workstation_id, now, now))
    conn.commit()


up = run
