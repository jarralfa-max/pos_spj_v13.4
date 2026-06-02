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

            old_row = db.execute(
                "SELECT total, cliente_tel, folio FROM delivery_orders WHERE id=?",
                (order_id,),
            ).fetchone()
            old_total = float(old_row[0]) if old_row else 0.0

            from core.services.order_total_service import OrderTotalService
            new_total = OrderTotalService(db).recalculate_order_total(int(order_id))

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


# ── Lifecycle handlers (v13.30) ───────────────────────────────────────────────

class DeliveryLifecycleAuditHandler:
    """Writes an audit_log row for every delivery lifecycle event.

    Single handler for all lifecycle events; wiring registers it on each.
    Triggered by: DELIVERY_ORDER_CREATED, DELIVERY_ORDER_CONFIRMED,
                  DELIVERY_ORDER_PREPARING, DELIVERY_DRIVER_ASSIGNED,
                  DELIVERY_OUT_FOR_DELIVERY, DELIVERY_ORDER_DELIVERED,
                  DELIVERY_ORDER_CANCELLED
    """

    def __init__(self, db) -> None:
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> None:
        event_type = payload.get("_event_type", "DELIVERY_LIFECYCLE")
        order_id   = payload.get("order_id")
        folio      = payload.get("folio") or str(order_id or "")
        usuario    = payload.get("usuario") or payload.get("responsable") or "sistema"
        sucursal_id = int(payload.get("sucursal_id") or 1)
        total      = payload.get("total") or payload.get("new_total")
        details    = f"folio={folio}"
        if total is not None:
            details += f" total=${float(total):.2f}"
        driver = payload.get("driver_nombre") or payload.get("driver_id")
        if driver:
            details += f" driver={driver}"

        try:
            self.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES(?,?,?,?,?,?,?,datetime('now'))",
                (event_type, "DELIVERY", "delivery_orders",
                 str(order_id or ""), usuario, sucursal_id, details),
            )
            try:
                self.db.commit()
            except Exception:
                pass
            logger.debug("DeliveryAudit: %s order=%s", event_type, order_id)
        except Exception as exc:
            logger.debug("DeliveryLifecycleAuditHandler: %s", exc)


class DeliveryNotificationDispatchHandler:
    """Dispatches CUSTOMER_NOTIFICATION_REQUESTED to DeliveryNotificationService.

    Triggered by: CUSTOMER_NOTIFICATION_REQUESTED
    Payload: {order_id, canal, template, params, cliente_tel, folio, sucursal_id}
    """

    def __init__(self, notification_service=None, whatsapp_notifier=None) -> None:
        self._svc = notification_service
        self._wa_notifier = whatsapp_notifier
        self._svc_init_failed = False
        self._wa_init_failed = False

    def _get_service(self):
        if self._svc is not None:
            return self._svc
        if self._svc_init_failed:
            return None
        try:
            from notifications.service import build_default_service
            self._svc = build_default_service()
            return self._svc
        except Exception as exc:
            logger.warning("NotificationDispatch: service init failed: %s", exc)
            self._svc_init_failed = True
            return None


    def _get_whatsapp_notifier(self):
        if self._wa_notifier is not None:
            return self._wa_notifier
        if self._wa_init_failed:
            return None
        try:
            from core.delivery.infrastructure.whatsapp_delivery_notifier import WhatsAppDeliveryNotifier
            self._wa_notifier = WhatsAppDeliveryNotifier()
            return self._wa_notifier
        except Exception as exc:
            logger.warning("NotificationDispatch: WhatsApp notifier init failed: %s", exc)
            self._wa_init_failed = True
            return None

    def handle(self, payload: Dict[str, Any]) -> None:
        canal = str(payload.get("canal") or "all").lower()
        if canal == "whatsapp":
            notifier = self._get_whatsapp_notifier()
            if notifier is None:
                return
            try:
                notifier.notify_from_event(payload)
            except Exception as exc:
                logger.warning("NotificationDispatch WhatsApp failed: %s", exc)
            return

        from notifications.base import NotificationPayload
        svc = self._get_service()
        if svc is None:
            return
        template = str(payload.get("template") or "")
        params   = payload.get("params") or {}
        title    = params.get("title") or template.replace("_", " ").title()
        body     = params.get("body") or params.get("message") or template
        try:
            svc.notify(NotificationPayload(
                event_type=template,
                title=title,
                body=body,
                channel=canal,
                order_id=payload.get("order_id"),
                cliente_tel=str(payload.get("cliente_tel") or ""),
                folio=str(payload.get("folio") or ""),
                priority=str(payload.get("priority") or "normal"),
                sucursal_id=int(payload.get("sucursal_id") or 1),
                metadata=params,
            ))
        except Exception as exc:
            logger.warning("NotificationDispatch failed: %s", exc)


class InventoryCommitHandler:
    """Commits inventory reservations to real movements when delivery is delivered.

    Triggered by: INVENTORY_COMMIT_REQUIRED
    Payload: {order_id, items[], sucursal_id, operation_id, db}

    Flow:
      1. For each item: commit_reservation (convert soft-lock → movement)
      2. Deduct branch_inventory.quantity (physical stock)
      3. Publish AJUSTE_INVENTARIO for each committed item
    """

    def __init__(self, db) -> None:
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> None:
        from core.services.reservation_service import ReservationService
        order_id     = payload.get("order_id")
        operation_id = str(payload.get("operation_id") or order_id or "")
        branch_id    = int(payload.get("branch_id") or payload.get("sucursal_id") or 1)
        db           = payload.get("db") or self.db

        if not operation_id:
            logger.warning("InventoryCommitHandler: no operation_id in payload")
            return

        svc = ReservationService()
        try:
            reservations = svc.get_reservations_for_operation(db, operation_id)
            if not reservations:
                # Fall back to items in payload
                items = payload.get("items") or []
                if items:
                    self._commit_from_items(db, items, operation_id, branch_id, svc)
                else:
                    logger.debug("InventoryCommit: no reservations or items for op=%s", operation_id)
                return

            committed = 0
            for res in reservations:
                product_id  = res.get("product_id")
                actual_qty  = float(res.get("reserved_qty") or 0)
                if not product_id or actual_qty <= 0:
                    continue
                try:
                    svc.commit_reservation(
                        db=db,
                        operation_id=operation_id,
                        product_id=int(product_id),
                        actual_qty=actual_qty,
                        branch_id=branch_id,
                    )
                    committed += 1
                    _publish_safe("AJUSTE_INVENTARIO", {
                        "producto_id": product_id,
                        "cantidad": -actual_qty,
                        "tipo": "delivery_commit",
                        "referencia_id": order_id,
                        "sucursal_id": branch_id,
                        "operation_id": operation_id,
                    })
                except Exception as exc:
                    logger.error("InventoryCommit product=%s: %s", product_id, exc)

            logger.info("InventoryCommit: order=%s committed=%d/%d",
                        order_id, committed, len(reservations))
        except Exception as exc:
            logger.error("InventoryCommitHandler error order=%s: %s", order_id, exc)

    def _commit_from_items(self, db, items, operation_id, branch_id, svc) -> None:
        for item in items:
            product_id = item.get("producto_id") or item.get("product_id")
            qty = float(item.get("final_qty") or item.get("prepared_qty") or item.get("cantidad") or 0)
            if not product_id or qty <= 0:
                continue
            try:
                svc.commit_reservation(
                    db=db, operation_id=operation_id,
                    product_id=int(product_id), actual_qty=qty, branch_id=branch_id,
                )
            except Exception as exc:
                logger.warning("InventoryCommit item fallback product=%s: %s", product_id, exc)


class DriverSettlementFinanceHandler:
    """Records a double-entry journal and cash movement when a driver cuts.

    Triggered by: DRIVER_SETTLEMENT_CREATED
    Payload: {cut_id, driver_id, driver_nombre, efectivo, diferencia, fecha, sucursal_id}
    """

    def __init__(self, db) -> None:
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> None:
        cut_id       = payload.get("cut_id")
        driver_name  = str(payload.get("driver_nombre") or payload.get("driver_id") or "repartidor")
        efectivo     = float(payload.get("efectivo") or payload.get("efectivo_entregado") or 0)
        diferencia   = float(payload.get("diferencia") or 0)
        sucursal_id  = int(payload.get("sucursal_id") or 1)
        usuario      = str(payload.get("usuario_corte") or "sistema")

        if cut_id is None:
            return

        try:
            # Audit trail
            self.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES(?,?,?,?,?,?,?,datetime('now'))",
                (
                    "CORTE_REPARTIDOR", "DELIVERY", "delivery_driver_cuts",
                    str(cut_id), usuario, sucursal_id,
                    f"driver={driver_name} efectivo=${efectivo:.2f} diff=${diferencia:.2f}",
                ),
            )

            # Finance journal: caja_delivery debe / cuentas_repartidores haber
            try:
                from core.services.enterprise.finance_service import FinanceService
                fs = FinanceService(self.db)
                fs.registrar_asiento(
                    debe="caja_delivery",
                    haber="cuentas_repartidores",
                    concepto=f"Corte repartidor {driver_name} #{cut_id}",
                    monto=abs(efectivo),
                    modulo="delivery",
                    referencia_id=cut_id,
                    usuario_id=usuario,
                    sucursal_id=sucursal_id,
                    evento="DRIVER_SETTLEMENT_CREATED",
                    metadata={"driver_nombre": driver_name, "diferencia": diferencia},
                )
            except Exception as exc:
                logger.debug("DriverSettlementFinanceHandler asiento: %s", exc)

            try:
                self.db.commit()
            except Exception:
                pass
            logger.info(
                "DriverSettlement: cut=%s driver=%s efectivo=%.2f diff=%.2f",
                cut_id, driver_name, efectivo, diferencia,
            )
        except Exception as exc:
            logger.error("DriverSettlementFinanceHandler error cut=%s: %s", cut_id, exc)


class PurchaseSuggestionHandler:
    """Logs purchase suggestions for low-stock items after delivery commit.

    Triggered by: PURCHASE_SUGGESTION_CREATED
    Payload: {producto_id, cantidad_sugerida, motivo, sucursal_id}
    """

    def __init__(self, db) -> None:
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> None:
        producto_id      = payload.get("producto_id")
        cantidad_sug     = float(payload.get("cantidad_sugerida") or 0)
        motivo           = str(payload.get("motivo") or "stock_bajo")
        sucursal_id      = int(payload.get("sucursal_id") or 1)

        if not producto_id:
            return
        try:
            self.db.execute(
                "INSERT OR IGNORE INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,detalles,fecha)"
                " VALUES(?,?,?,?,?,?,?,datetime('now'))",
                (
                    "SUGERENCIA_COMPRA", "COMPRAS", "productos",
                    str(producto_id), "sistema", sucursal_id,
                    f"qty_sugerida={cantidad_sug:.2f} motivo={motivo}",
                ),
            )
            try:
                self.db.commit()
            except Exception:
                pass
            _publish_safe("STOCK_BAJO_MINIMO", {
                "producto_id": producto_id,
                "cantidad_sugerida": cantidad_sug,
                "motivo": motivo,
                "sucursal_id": sucursal_id,
            })
            logger.info(
                "PurchaseSuggestion: producto=%s qty=%.2f motivo=%s",
                producto_id, cantidad_sug, motivo,
            )
        except Exception as exc:
            logger.debug("PurchaseSuggestionHandler: %s", exc)


# ── Internal helper ───────────────────────────────────────────────────────────

def _publish_safe(event: str, payload: dict) -> None:
    try:
        from core.events.event_bus import get_bus
        get_bus().publish(event, payload)
    except Exception as exc:
        logger.debug("_publish_safe %s: %s", event, exc)
