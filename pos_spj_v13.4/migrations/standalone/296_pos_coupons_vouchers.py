"""296 — cupones y vales en la caja (2026-10-03).

Decisiones del usuario: el cupón es un DESCUENTO del ticket y el vale (o saldo
a favor) una FORMA DE PAGO que cancela su pasivo.

* `sale_coupons`: los cupones que Fidelidad aprobó y apartó para cada venta.
* Permiso `POS.pago.vale` (cobrar con vale): mismo reparto que los demás pagos
  de contado de la 268 — cajero, gerente, admin y dueño. `INSERT OR IGNORE`:
  no pisa lo que un administrador haya revocado; un rol ausente se omite.

Idempotente.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.296")

POS_ACTIONS = ("pago.vale",)
_ROLES = ("system_owner", "admin", "gerente", "cajero")


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def run(conn) -> None:
    from backend.infrastructure.db.schema.sales_schema import create_sales_schema

    if _tabla(conn, "sales"):
        create_sales_schema(conn)
    concedidos = 0
    if _tabla(conn, "roles") and _tabla(conn, "rol_permisos"):
        for rol in _ROLES:
            fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                                (rol,)).fetchone()
            if fila is None:
                continue
            for accion in POS_ACTIONS:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                    " VALUES (?,?,?,?,1)", (new_uuid(), str(fila[0]), "POS", accion))
                concedidos += max(cur.rowcount or 0, 0)
    conn.commit()
    logger.info("296: cupones en venta listos; %s permisos de cobro con vale.", concedidos)


up = run
