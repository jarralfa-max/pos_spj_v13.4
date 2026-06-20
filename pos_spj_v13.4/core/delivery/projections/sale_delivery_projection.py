from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from core.delivery.domain.states import DeliveryStatus, normalize_status

logger = logging.getLogger("spj.delivery.projections.sales")


class SaleDeliveryProjectionService:
    """Projects logistical delivery state into the commercial sale record.

    Source of truth remains `delivery_orders` for logistics. `ventas` is updated
    only through this projection as a secondary commercial/fiscal view.
    """

    STATUS_TO_SALE_STATUS: Mapping[DeliveryStatus, str] = {
        DeliveryStatus.PENDIENTE: "pendiente_wa",
        DeliveryStatus.PREPARACION: "en_preparacion",
        DeliveryStatus.EN_RUTA: "en_ruta",
        DeliveryStatus.ENTREGADO: "entregada",
        DeliveryStatus.CANCELADO: "cancelada",
    }

    def __init__(self, db) -> None:
        self.db = db

    def project_status_for_order(self, order: Mapping[str, Any] | None, status: str | DeliveryStatus) -> bool:
        if not order:
            return False
        return self.project_status(order.get("venta_id"), status)

    def project_status(self, venta_id: Any, status: str | DeliveryStatus) -> bool:
        if not venta_id or not self._has_column("ventas", "estado"):
            return False
        sale_status = self.STATUS_TO_SALE_STATUS.get(normalize_status(status))
        if not sale_status:
            return False
        try:
            self.db.execute("UPDATE ventas SET estado=? WHERE id=?", (sale_status, int(venta_id)))
        except Exception as exc:
            # The ventas table may have a state-machine trigger (trg_protect_sale_estado)
            # that only allows transitions from 'completada'/'CANCEL_PENDING'. Delivery
            # logistics is the source of truth; ventas projection is secondary and must
            # never abort the delivery state transition.
            logger.warning(
                "project_status: ventas.estado projection skipped venta_id=%s "
                "delivery_status=%s → sale_status=%s: %s",
                venta_id, status, sale_status, exc,
            )
            return False
        return True

    def project_total_for_order(self, order: Mapping[str, Any] | None, total: float) -> bool:
        if not order:
            return False
        return self.project_total(order.get("venta_id"), total)

    def project_total(self, venta_id: Any, total: float) -> bool:
        if not venta_id or not self._has_column("ventas", "total"):
            return False
        self.db.execute("UPDATE ventas SET total=? WHERE id=?", (float(total), int(venta_id)))
        return True

    def project_scheduled_activation(self, venta_id: Any, workflow_type: str) -> bool:
        if not venta_id:
            return False
        columns = self._columns("ventas")
        assignments: list[str] = []
        values: list[Any] = []
        if "workflow_type" in columns:
            assignments.append("workflow_type=?")
            values.append(workflow_type)
        if "estado" in columns:
            assignments.append("estado=?")
            values.append("pendiente")
        if not assignments:
            return False
        values.append(int(venta_id))
        self.db.execute(f"UPDATE ventas SET {', '.join(assignments)} WHERE id=?", tuple(values))
        return True

    def _has_column(self, table: str, column: str) -> bool:
        return column in self._columns(table)

    def _columns(self, table: str) -> set[str]:
        try:
            return {row[1] for row in self.db.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception as exc:
            logger.debug("No se pudieron consultar columnas de %s: %s", table, exc)
            return set()
