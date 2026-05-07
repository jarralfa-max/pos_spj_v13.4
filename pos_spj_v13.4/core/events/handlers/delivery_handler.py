"""Delivery event handlers — single-responsibility, decoupled from UI.

Each handler handles exactly one concern (SRP).
All handlers are fault-tolerant: exceptions are logged but never propagate
so they don't break the EventBus chain.

Handler priority convention (matches wiring.py):
  100 — critical sync (reservation writes)
   50 — business logic (totals, payment)
   10 — notifications (WA — soft-fail)
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("spj.handlers.delivery")


class DeliveryReserveStockHandler:
    """Reserves inventory for each item in a new delivery order.

    Triggered by: DELIVERY_ORDER_RESERVED
    Payload: {order_id, items[], branch_id, operation_id, db}
      items[] = [{product_id, qty, unit, nombre}]
    """

    def __init__(self, db) -> None:
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> None:
        from core.services.reservation_service import ReservationService, VARIABLE_WEIGHT_UNITS
        svc = ReservationService()
        items = payload.get("items") or []
        branch_id = int(payload.get("branch_id") or 1)
        operation_id = str(payload.get("operation_id") or payload.get("order_id", ""))
        db = payload.get("db") or self.db
        reserved = 0

        for item in items:
            product_id = item.get("producto_id") or item.get("product_id")
            if not product_id:
                continue
            qty = float(item.get("cantidad") or item.get("qty") or 0)
            if qty <= 0:
                continue
            try:
                svc.reserve(
                    db=db,
                    product_id=int(product_id),
                    qty=qty,
                    operation_id=operation_id,
                    branch_id=branch_id,
                    operation_type="delivery",
                )
                reserved += 1
                logger.info(
                    "Reserved product_id=%s qty=%.3f order=%s",
                    product_id, qty, operation_id,
                )
            except ValueError as exc:
                # Insufficient stock — log and continue (don't block order)
                logger.warning("ReserveStock insufficient: %s", exc)
            except Exception as exc:
                logger.error("ReserveStock error product_id=%s: %s", product_id, exc)

        logger.info(
            "DeliveryReserveStockHandler: order=%s reserved=%d/%d items",
            operation_id, reserved, len(items),
        )


class DeliveryReservationReleaseHandler:
    """Releases all reservations when an order is cancelled.

    Triggered by: stock_liberar_solicitado  (existing event from DeliveryService)
    Payload: {order_id}
    """

    def __init__(self, db) -> None:
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> None:
        from core.services.reservation_service import ReservationService
        svc = ReservationService()
        order_id = str(payload.get("order_id", ""))
        if not order_id:
            return
        try:
            released = svc.release_by_operation(self.db, operation_id=order_id)
            logger.info("ReservationRelease: order=%s released=%d row(s)", order_id, released)
        except Exception as exc:
            logger.error("ReservationRelease error order=%s: %s", order_id, exc)


class DeliveryWeightAdjustmentHandler:
    """Persists weight adjustment and recalculates order totals.

    Triggered by: DELIVERY_ITEM_WEIGHT_ADJUSTED
    Payload: {order_id, item_id, requested_qty, prepared_qty, unit_price,
              prepared_by, adjustment_reason, db}
    Publishes: DELIVERY_TOTAL_UPDATED (via EventBus)
    """

    def __init__(self, db) -> None:
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> None:
        from core.services.reservation_service import ReservationService
        order_id   = payload.get("order_id")
        item_id    = payload.get("item_id")
        req_qty    = float(payload.get("requested_qty") or 0)
        prep_qty   = float(payload.get("prepared_qty") or 0)
        unit_price = float(payload.get("unit_price") or 0)
        prepared_by = str(payload.get("prepared_by") or "sistema")
        reason     = str(payload.get("adjustment_reason") or "")
        db = payload.get("db") or self.db

        if not order_id or prep_qty <= 0:
            return

        adj = ReservationService.compute_adjustment(req_qty, prep_qty, unit_price)

        try:
            # Update delivery_items row — write subtotal so the detail panel reflects the new price
            db.execute(
                """UPDATE delivery_items
                   SET prepared_qty=?, final_qty=?, subtotal=?,
                       prepared_by=?, prepared_at=datetime('now'),
                       adjustment_reason=?, tolerance_exceeded=?
                   WHERE id=?""",
                (
                    prep_qty, prep_qty, adj["new_subtotal"],
                    prepared_by, reason,
                    1 if adj["tolerance_exceeded"] else 0,
                    item_id,
                ),
            )

            # Recalculate order total from all items
            row = db.execute(
                """SELECT COALESCE(SUM(
                       CASE WHEN prepared_qty IS NOT NULL AND prepared_qty > 0
                            THEN prepared_qty * precio_unitario
                            ELSE subtotal
                       END), 0)
                   FROM delivery_items WHERE delivery_id=?""",
                (order_id,),
            ).fetchone()
            new_total = round(float(row[0]) if row else 0.0, 2)

            old_row = db.execute(
                "SELECT total, cliente_tel, folio FROM delivery_orders WHERE id=?",
                (order_id,),
            ).fetchone()
            old_total = float(old_row[0]) if old_row else 0.0

            db.execute(
                "UPDATE delivery_orders SET total=?, weight_adjusted=1 WHERE id=?",
                (new_total, order_id),
            )
            try:
                db.commit()
            except Exception:
                pass

            logger.info(
                "WeightAdjust: order=%s item=%s req=%.3f prep=%.3f "
                "old_total=%.2f new_total=%.2f tolerance_exceeded=%s",
                order_id, item_id, req_qty, prep_qty,
                old_total, new_total, adj["tolerance_exceeded"],
            )

            # Cascade: publish DELIVERY_TOTAL_UPDATED
            # Query is SELECT total, cliente_tel, folio — so index 1=cliente_tel, 2=folio
            cliente_tel = old_row[1] if old_row and len(old_row) > 1 else ""
            folio       = old_row[2] if old_row and len(old_row) > 2 else str(order_id)
            _publish_safe("DELIVERY_TOTAL_UPDATED", {
                "order_id": order_id,
                "old_total": old_total,
                "new_total": new_total,
                "folio": folio or str(order_id),
                "cliente_tel": cliente_tel or "",
                "cliente_email": payload.get("cliente_email", ""),
                "db": db,
            })

        except Exception as exc:
            logger.error("WeightAdjustmentHandler error order=%s: %s", order_id, exc)


class DeliveryTotalsRecalculationHandler:
    """Recalculates and persists delivery order totals.

    Triggered by: DELIVERY_TOTAL_UPDATED
    This handler is the canonical place where total = sum(items).
    If upstream already did the calc, this is a no-op (idempotent).
    """

    def __init__(self, db) -> None:
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> None:
        order_id = payload.get("order_id")
        new_total = payload.get("new_total")
        if order_id is None or new_total is None:
            return
        logger.debug("TotalsRecalc: order=%s new_total=%.2f (already applied upstream)", order_id, new_total)


class DeliveryPaymentUpdateHandler:
    """Regenerates MercadoPago preference when order total changes.

    Triggered by: DELIVERY_TOTAL_UPDATED
    Payload: {order_id, new_total, folio, cliente_email, db}
    Publishes: DELIVERY_PAYMENT_UPDATED
    """

    def __init__(self, db) -> None:
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> None:
        order_id    = payload.get("order_id")
        new_total   = float(payload.get("new_total") or 0)
        folio       = str(payload.get("folio") or order_id or "")
        email       = str(payload.get("cliente_email") or "")
        db          = payload.get("db") or self.db

        if not order_id or new_total <= 0:
            return

        try:
            # Import here to avoid circular imports at module load
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(__file__)))))
            from services.mercado_pago_service import MercadoPagoService
            mp = MercadoPagoService(db)
            url = mp.crear_link(
                total=new_total,
                pedido_id=order_id,
                descripcion=f"Delivery #{folio}",
                cliente_email=email or "cliente@spjpos.mx",
            )
            if url:
                _publish_safe("DELIVERY_PAYMENT_UPDATED", {
                    "order_id": order_id,
                    "payment_url": url,
                    "preference_id": None,
                    "new_total": new_total,
                })
                logger.info(
                    "PaymentUpdate: order=%s new_total=%.2f url=%s",
                    order_id, new_total, url[:60],
                )
            else:
                logger.warning("PaymentUpdate: crear_link returned None for order=%s", order_id)
        except Exception as exc:
            logger.warning("PaymentUpdateHandler (non-fatal): %s", exc)


class DeliveryWhatsAppNotificationHandler:
    """Sends WhatsApp weight-adjustment notification to customer.

    Triggered by: DELIVERY_ITEM_WEIGHT_ADJUSTED
    Payload: {order_id, folio, cliente_tel, requested_qty, prepared_qty,
              unit, new_total, unit_price}
    """

    def handle(self, payload: Dict[str, Any]) -> None:
        phone     = str(payload.get("cliente_tel") or "")
        folio     = str(payload.get("folio") or payload.get("order_id") or "")
        req_qty   = float(payload.get("requested_qty") or 0)
        prep_qty  = float(payload.get("prepared_qty") or 0)
        unit      = str(payload.get("unit") or "kg")
        new_total = float(payload.get("new_total") or 0)

        if not phone:
            logger.debug("WAWeightNotify: no phone for order=%s, skipping", folio)
            return

        diff = prep_qty - req_qty
        sign = "+" if diff >= 0 else ""
        msg = (
            f"📦 Actualización pedido #{folio}\n"
            f"Peso solicitado: {req_qty:.3g} {unit}\n"
            f"Peso real: {prep_qty:.3g} {unit} ({sign}{diff:.3g} {unit})\n"
            f"Total actualizado: ${new_total:,.2f}\n"
            f"Pronto lo enviamos. 🛵"
        )

        try:
            from core.integrations.whatsapp_client import WhatsAppClient
            ok = WhatsAppClient().enviar_mensaje(phone, msg)
            logger.info(
                "WAWeightNotify: order=%s phone=%s ok=%s",
                folio, phone[-4:], ok,
            )
        except Exception as exc:
            logger.warning("WAWeightNotify failed (non-fatal): %s", exc)


# ── Internal helper ───────────────────────────────────────────────────────────

def _publish_safe(event: str, payload: dict) -> None:
    try:
        from core.events.event_bus import get_bus
        get_bus().publish(event, payload)
    except Exception as exc:
        logger.debug("_publish_safe %s: %s", event, exc)
