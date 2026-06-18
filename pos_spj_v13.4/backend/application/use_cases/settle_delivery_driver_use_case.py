"""Settle delivered orders for a driver (corte de repartidor)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.delivery.application.settle_driver")

DRIVER_SETTLEMENT_CREATED = "DRIVER_SETTLEMENT_CREATED"


@dataclass(frozen=True)
class SettleDeliveryDriverCommand:
    """Input for a driver settlement cut."""

    driver_id: int
    driver_nombre: str
    order_ids: list[int] = field(default_factory=list)
    efectivo_entregado: float = 0.0
    notas: str = ""
    usuario: str = "sistema"
    sucursal_id: int = 0
    turno_inicio: str = ""
    # Pre-computed totals (supplied by UI after loading orders)
    efectivo_cobrado: float = 0.0
    tarjeta_cobrado: float = 0.0
    transfer_cobrado: float = 0.0

    def __post_init__(self) -> None:
        if not self.driver_id:
            raise ValueError("driver_id es requerido")
        if not self.order_ids:
            raise ValueError("order_ids no puede estar vacío")


class SettleDeliveryDriverUseCase:
    """Create a driver settlement cut atomically.

    Inserts one row in ``delivery_driver_cuts`` plus one row per order in
    ``delivery_cut_items``, then marks each delivery order with the cut id.
    Emits DRIVER_SETTLEMENT_CREATED through the publisher.
    """

    def __init__(self, db, publisher=None) -> None:
        self._db = db
        self._publisher = publisher or (lambda *_: None)

    def execute(self, cmd: SettleDeliveryDriverCommand) -> dict[str, Any]:
        total_cobrado = cmd.efectivo_cobrado + cmd.tarjeta_cobrado + cmd.transfer_cobrado
        diferencia = cmd.efectivo_entregado - cmd.efectivo_cobrado
        cut_id = new_uuid()

        self._db.execute(
            """
            INSERT INTO delivery_driver_cuts
                (id, driver_id, driver_nombre, turno_inicio,
                 entregas_total, efectivo_cobrado, tarjeta_cobrado,
                 transfer_cobrado, total_cobrado, efectivo_entregado,
                 diferencia, usuario_corte, sucursal_id, notas)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                cut_id,
                cmd.driver_id,
                cmd.driver_nombre,
                cmd.turno_inicio or None,
                len(cmd.order_ids),
                cmd.efectivo_cobrado,
                cmd.tarjeta_cobrado,
                cmd.transfer_cobrado,
                total_cobrado,
                cmd.efectivo_entregado,
                diferencia,
                cmd.usuario,
                cmd.sucursal_id,
                cmd.notas or None,
            ),
        )

        for order_id in cmd.order_ids:
            item_id = new_uuid()
            # Fetch order details for the cut item record
            try:
                row = self._db.execute(
                    "SELECT cliente_nombre, COALESCE(total,0), pago_metodo, COALESCE(pago_monto,0)"
                    " FROM delivery_orders WHERE id=?",
                    (order_id,),
                ).fetchone()
            except Exception:
                row = None

            self._db.execute(
                """
                INSERT INTO delivery_cut_items
                    (id, cut_id, order_id, cliente_nombre, total, pago_metodo, pago_monto)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    item_id,
                    cut_id,
                    order_id,
                    row[0] if row else "",
                    float(row[1]) if row else 0.0,
                    row[2] if row else "",
                    float(row[3]) if row else 0.0,
                ),
            )

            try:
                self._db.execute(
                    "UPDATE delivery_orders SET corte_id=? WHERE id=?",
                    (cut_id, order_id),
                )
            except Exception:
                logger.warning("No se pudo marcar corte_id en order %s", order_id)

        self._db.commit()

        payload: dict[str, Any] = {
            "cut_id": cut_id,
            "driver_id": cmd.driver_id,
            "driver_nombre": cmd.driver_nombre,
            "total_cobrado": total_cobrado,
            "efectivo_entregado": cmd.efectivo_entregado,
            "diferencia": diferencia,
            "sucursal_id": cmd.sucursal_id,
            "usuario_corte": cmd.usuario,
            "order_count": len(cmd.order_ids),
        }
        self._publisher(DRIVER_SETTLEMENT_CREATED, payload)

        logger.info(
            "Driver settlement created cut_id=%s driver=%s orders=%d diferencia=%.2f",
            cut_id,
            cmd.driver_id,
            len(cmd.order_ids),
            diferencia,
        )
        return {"cut_id": cut_id, "total_cobrado": total_cobrado, "diferencia": diferencia}
