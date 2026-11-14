"""368 — siembra `POS.venta.reanudar_ajena` (SDLC-ARQ-SESS-003).

Reanudar la venta suspendida de otro cajero deja de estar abierto a todo el que
tenga `POS.venta.reanudar`: exige este permiso nuevo, que es también el que hace
falta para autorizar a otro cajero. Decisión del responsable (2026-11-02): un
supervisor sí puede, y otro cajero con autorización también.

REPARTO: mismo criterio que la 268, "cajero vende, gerente autoriza". El cajero
NO lo recibe: reanuda las suyas y para las ajenas pide autorización. El rol
`supervisor` no existe en el sembrado base; si una instalación lo creó, lo
recibe. Un rol que no exista se OMITE, nunca se crea. `INSERT OR IGNORE`: no pisa
lo que un administrador ya haya otorgado o revocado.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.368")

POS_ACTIONS = ("venta.reanudar_ajena",)
_ROLES = ("system_owner", "admin", "gerente", "supervisor")


def run(conn) -> None:
    tablas = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('roles','rol_permisos')")}
    if tablas != {"roles", "rol_permisos"}:
        logger.info("368: sin tablas de roles/permisos; nada que sembrar.")
        return
    concedidos = 0
    for rol in _ROLES:
        fila = conn.execute(
            "SELECT id FROM roles WHERE lower(trim(nombre))=?", (rol,)).fetchone()
        if fila is None:
            continue
        for accion in POS_ACTIONS:
            cur = conn.execute(
                "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                " VALUES (?,?,?,?,1)", (new_uuid(), str(fila[0]), "POS", accion))
            concedidos += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()
    logger.info("368: %s concesiones de POS.venta.reanudar_ajena", concedidos)


up = run
