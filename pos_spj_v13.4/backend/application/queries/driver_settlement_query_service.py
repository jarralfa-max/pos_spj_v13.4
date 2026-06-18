"""Read-only query service for driver settlement data."""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.delivery.queries.driver_settlement")


class DriverSettlementQueryService:
    """Read-only service for driver settlement (corte de repartidor) queries."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def list_pending_orders_for_driver(
        self, driver_id: int, sucursal_id: int = 0
    ) -> list[dict]:
        """Return ENTREGADO orders for a driver not yet included in any settlement cut.

        Args:
            driver_id: Driver primary key.
            sucursal_id: Optional branch filter (0 = all branches).

        Returns:
            List of dicts with keys: id, cliente_nombre, total, pago_metodo,
            pago_monto, fecha_entrega.
        """
        # Use corte_id column as the canonical exclusion (set by SettleDeliveryDriverUseCase).
        # delivery_cut_items is an additional cross-reference but corte_id is the authority.
        try:
            rows = self._conn.execute(
                """
                SELECT id,
                       COALESCE(cliente_nombre, '') AS cliente_nombre,
                       COALESCE(total, 0)           AS total,
                       COALESCE(pago_metodo, '')    AS pago_metodo,
                       COALESCE(pago_monto, 0)      AS pago_monto,
                       fecha_entrega
                  FROM delivery_orders
                 WHERE driver_id = ?
                   AND estado    = 'entregado'
                   AND (? = 0 OR sucursal_id = ?)
                   AND COALESCE(corte_id, '') = ''
                 ORDER BY fecha_entrega DESC
                """,
                (driver_id, sucursal_id, sucursal_id),
            ).fetchall()
        except Exception:
            logger.exception(
                "Error listing pending settlement orders driver_id=%s", driver_id
            )
            return []

        return [
            {
                "id": row[0],
                "cliente_nombre": row[1],
                "total": float(row[2] or 0),
                "pago_metodo": row[3],
                "pago_monto": float(row[4] or 0),
                "fecha_entrega": row[5],
            }
            for row in rows
        ]

    def list_cut_history(
        self, driver_id: int, sucursal_id: int = 0, limit: int = 50
    ) -> list[dict]:
        """Return past settlement cuts for a driver.

        Args:
            driver_id: Driver primary key.
            sucursal_id: Optional branch filter (0 = all branches).
            limit: Maximum rows to return.

        Returns:
            List of dicts with cut summary data.
        """
        try:
            rows = self._conn.execute(
                """
                SELECT id, driver_nombre, turno_inicio, turno_fin,
                       entregas_total, efectivo_cobrado, tarjeta_cobrado,
                       transfer_cobrado, total_cobrado, efectivo_entregado,
                       diferencia, usuario_corte, notas, created_at
                  FROM delivery_driver_cuts
                 WHERE driver_id = ?
                   AND (? = 0 OR sucursal_id = ?)
                 ORDER BY created_at DESC
                 LIMIT ?
                """,
                (driver_id, sucursal_id, sucursal_id, limit),
            ).fetchall()
        except Exception:
            logger.exception(
                "Error listing settlement history driver_id=%s", driver_id
            )
            return []

        keys = [
            "id", "driver_nombre", "turno_inicio", "turno_fin",
            "entregas_total", "efectivo_cobrado", "tarjeta_cobrado",
            "transfer_cobrado", "total_cobrado", "efectivo_entregado",
            "diferencia", "usuario_corte", "notas", "created_at",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def get_payment_summary(self, order_rows: list[dict]) -> dict:
        """Compute efectivo/tarjeta/transferencia totals from a list of order rows.

        Each row must have 'pago_metodo' and 'pago_monto' keys.
        Returns dict with keys: efectivo, tarjeta, transfer, total.
        """
        efe = tar = tra = 0.0
        for row in order_rows:
            monto = float(row.get("pago_monto") or 0)
            metodo = str(row.get("pago_metodo") or "").lower()
            if "efect" in metodo:
                efe += monto
            elif "tarjeta" in metodo or "card" in metodo:
                tar += monto
            elif "transfer" in metodo:
                tra += monto
        return {"efectivo": efe, "tarjeta": tar, "transfer": tra, "total": efe + tar + tra}
