from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable
from typing import Any

from core.delivery.domain.events import DeliveryEvents
from core.delivery.domain.policies import WeightAdjustmentPolicy

from .ports import EventPublisher, NoopPublisher

logger = logging.getLogger("spj.delivery.application.adjustment")

ADJUSTMENT_PENDING = "pending_customer"
ADJUSTMENT_ACCEPTED = "accepted"
TOLERANCE_UNITS = float(os.environ.get("DELIVERY_WEIGHT_TOLERANCE_UNITS", "0.2"))


class AdjustDeliveryWeightUseCase:
    def __init__(
        self,
        *,
        db,
        repository,
        publisher: EventPublisher = NoopPublisher,
        notify_adjustment_pending: Callable[[dict[str, Any], str, float, float, str, float, float], bool] | None = None,
        recalculate_order_total: Callable[[int], float] | None = None,
        sync_sale_total: Callable[[int, float], None] | None = None,
        outbox_repository=None,
        adjust_reservation: Callable[[str, int, float, int], int] | None = None,
    ) -> None:
        self.db = db
        self.repository = repository
        self.publisher = publisher
        self.notify_adjustment_pending = notify_adjustment_pending or (lambda *_args: False)
        self.recalculate_order_total = recalculate_order_total
        self.sync_sale_total = sync_sale_total or (lambda _order_id, _new_total: None)
        self.outbox_repository = outbox_repository
        # Re-adjusts the inventory soft-lock to the real prepared quantity.
        # Signature: (operation_id, product_id, new_qty, branch_id) -> rows_updated
        self.adjust_reservation = adjust_reservation

    def _enqueue(self, event_type: str, order_id: int, payload: dict[str, Any], operation_id: str | None = None) -> None:
        if self.outbox_repository is None:
            return
        self.outbox_repository.enqueue(
            event_type=event_type,
            aggregate_id=order_id,
            payload=payload,
            operation_id=operation_id,
            commit=False,
        )

    def execute(
        self,
        order_id: int,
        item_id: int,
        prepared_qty: float,
        prepared_by: str,
        adjustment_reason: str = "",
        unit: str = "kg",
    ) -> dict[str, Any]:
        order = self.repository.get_order(order_id) or {}
        estado = (order.get("estado") or "").lower()
        if estado != "preparacion":
            raise ValueError("El ajuste de peso/cantidad solo puede hacerse en estado 'preparacion'.")

        item_row = self.repository.get_item_for_weight_adjustment(order_id, item_id)
        if not item_row:
            raise ValueError(f"delivery_items.id={item_id} not found for order={order_id}")

        unit_price = float(item_row.get("precio_unitario") or 0)
        requested_qty = float(item_row.get("cantidad") or prepared_qty)
        item_name = item_row.get("nombre") or "Producto"
        decision = WeightAdjustmentPolicy(tolerance_units=TOLERANCE_UNITS).evaluate(
            requested_qty, prepared_qty, unit_price
        )
        adj = {
            "diff_qty": decision.diff_qty,
            "diff_abs": round(abs(decision.diff_qty), 4),
            "diff_pct": decision.diff_pct,
            "new_subtotal": decision.new_subtotal,
            "tolerance_units": decision.tolerance_units,
            "tolerance_exceeded": decision.tolerance_exceeded,
        }

        old_total = round(float(order.get("total") or 0), 2)

        if adj["tolerance_exceeded"]:
            token = uuid.uuid4().hex
            self.repository.mark_item_adjustment_pending(
                order_id=order_id,
                item_id=item_id,
                prepared_qty=prepared_qty,
                pending_subtotal=adj["new_subtotal"],
                token=token,
                tolerance_units=adj["tolerance_units"],
                prepared_by=prepared_by,
                adjustment_reason=adjustment_reason,
                commit=self.outbox_repository is None,
            )
            approval_payload = {
                "order_id": order_id,
                "item_id": item_id,
                "folio": order.get("folio") or str(order_id),
                "cliente_tel": order.get("cliente_tel", ""),
                "requested_qty": requested_qty,
                "prepared_qty": prepared_qty,
                "new_subtotal": adj["new_subtotal"],
                "diff_qty": adj["diff_qty"],
                "tolerance_units": adj["tolerance_units"],
            }
            self._enqueue(
                DeliveryEvents.ADJUSTMENT_APPROVAL_REQUIRED.value,
                order_id,
                approval_payload,
                operation_id=f"delivery:{order_id}:item:{item_id}:adjustment:{token}",
            )
            self._enqueue(
                DeliveryEvents.CUSTOMER_NOTIFICATION_REQUESTED.value,
                order_id,
                {
                    "order_id": order_id,
                    "canal": "whatsapp",
                    "template": "adjustment_required",
                    "params": approval_payload,
                    "cliente_tel": order.get("cliente_tel", ""),
                },
                operation_id=f"delivery:{order_id}:item:{item_id}:notify_adjustment:{token}",
            )
            if self.outbox_repository is not None:
                self.db.commit()
            self.publisher("DELIVERY_ADJUSTMENT_APPROVAL_REQUIRED", approval_payload)
            if self.outbox_repository is None:
                self.notify_adjustment_pending(
                    order, item_name, requested_qty, prepared_qty, unit,
                    adj["new_subtotal"], adj["diff_qty"]
                )
            return {**adj, "status": ADJUSTMENT_PENDING, "applied": False}

        self.repository.apply_item_weight_adjustment(
            order_id=order_id,
            item_id=item_id,
            prepared_qty=prepared_qty,
            subtotal=adj["new_subtotal"],
            prepared_by=prepared_by,
            adjustment_reason=adjustment_reason,
        )

        # ── Re-adjust inventory soft-lock to the real prepared quantity ──────────
        # The reservation was created at order creation with the requested qty.
        # After a real weight/quantity adjustment the lock must reflect the
        # prepared qty so available stock stays accurate. Idempotent (absolute set).
        product_id = item_row.get("producto_id") or item_row.get("product_id")
        branch_id = order.get("sucursal_id") or 1
        if self.adjust_reservation is not None and product_id:
            operation_id = f"delivery:{order_id}"
            try:
                self.adjust_reservation(operation_id, product_id, prepared_qty, branch_id)
                self._enqueue(
                    DeliveryEvents.INVENTORY_RESERVATION_ADJUSTED.value,
                    order_id,
                    {
                        "order_id": order_id,
                        "operation_id": operation_id,
                        "product_id": product_id,
                        "branch_id": branch_id,
                        "new_qty": prepared_qty,
                    },
                    operation_id=f"{operation_id}:item:{item_id}:reservation:{prepared_qty}",
                )
            except Exception as exc:
                # A reservation-adjustment failure must not lose the weight change;
                # surface it in logs but keep the accepted adjustment.
                logger.warning(
                    "No se pudo ajustar la reserva order=%s product=%s: %s",
                    order_id, product_id, exc,
                )

        if self.recalculate_order_total is None:
            raise RuntimeError("recalculate_order_total dependency is required")
        new_total = self.recalculate_order_total(order_id)
        self.sync_sale_total(order_id, new_total)
        total_payload = {
            "order_id": order_id,
            "old_total": old_total,
            "new_total": new_total,
            "folio": order.get("folio") or str(order_id),
            "cliente_tel": order.get("cliente_tel", ""),
            "cliente_email": order.get("cliente_email", ""),
        }
        self._enqueue(
            DeliveryEvents.TOTAL_UPDATED.value,
            order_id,
            total_payload,
            operation_id=f"delivery:{order_id}:item:{item_id}:total:{prepared_qty}",
        )
        self.db.commit()

        self.publisher(DeliveryEvents.ITEM_WEIGHT_ADJUSTED.value, {
            "order_id": order_id,
            "item_id": item_id,
            "item_name": item_name,
            "requested_qty": requested_qty,
            "prepared_qty": prepared_qty,
            "unit_price": unit_price,
            "unit": unit,
            "prepared_by": prepared_by,
            "adjustment_reason": adjustment_reason,
            "new_total": new_total,
            "folio": order.get("folio") or str(order_id),
            "cliente_tel": order.get("cliente_tel", ""),
            "cliente_email": order.get("cliente_email", ""),
        })
        self.publisher(DeliveryEvents.TOTAL_UPDATED.value, total_payload)
        logger.info(
            "adjust_item_weight: order=%s item=%s requested=%.3f prepared=%.3f diff=%.3f tolerance_units=%.3f exceeded=%s",
            order_id, item_id, requested_qty, prepared_qty,
            adj["diff_qty"], adj["tolerance_units"], adj["tolerance_exceeded"],
        )
        return {**adj, "status": ADJUSTMENT_ACCEPTED, "applied": True, "new_total": new_total}
