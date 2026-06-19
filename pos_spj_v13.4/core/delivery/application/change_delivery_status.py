from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from core.delivery.domain.events import DeliveryEvents
from core.delivery.domain.state_machine import DeliveryStateMachine
from core.delivery.projections.sale_delivery_projection import SaleDeliveryProjectionService

from .ports import EventPublisher, NoopPublisher, StatusNotifier

logger = logging.getLogger("spj.delivery.application.status")


class ChangeDeliveryStatusUseCase:
    def __init__(
        self,
        *,
        db,
        repository,
        sale_projection: SaleDeliveryProjectionService | None = None,
        whatsapp_service: StatusNotifier | None = None,
        publisher: EventPublisher = NoopPublisher,
        get_order_items: Callable[[int], list[dict[str, Any]]] | None = None,
        outbox_repository=None,
        inventory_service=None,
    ) -> None:
        self.db = db
        self.repository = repository
        self.sale_projection = sale_projection
        self.whatsapp_service = whatsapp_service
        self.publisher = publisher
        self.get_order_items = get_order_items or (lambda _order_id: [])
        self.outbox_repository = outbox_repository
        self.inventory_service = inventory_service

    def execute(
        self,
        order_id: int,
        status: str,
        usuario: str,
        responsable: str = "",
        observacion: str = "",
        pago_metodo: str = "",
        pago_monto: float = 0.0,
    ) -> None:
        sm = DeliveryStateMachine()
        target = sm.normalize_status(status).value

        # Full state machine validation — checks the allowed-transitions map
        order_before = self.repository.get_order(order_id)
        if order_before is None:
            raise ValueError(f"Pedido {order_id} no encontrado")
        logger.debug("execute: order_id=%s current=%s target=%s", order_id, order_before.get("estado"), target)

        # Pending adjustment check has priority over transition validation
        if target in ("en_ruta", "entregado") and self._has_pending_adjustment(order_id):
            self.repository.mark_adjustment_blocked(order_id, target)
            raise ValueError(
                "No se puede cambiar de estado: hay un ajuste de peso/cantidad pendiente de aceptación del cliente."
            )

        # Merge runtime params so the state machine sees responsable/driver
        _order_check = dict(order_before)
        if responsable:
            _order_check["responsable"] = responsable
        sm.assert_can_transition(_order_check, target)

        self._validate_workflow_transition(order_id, target)

        if target == "entregado" and not responsable:
            raise ValueError("No se puede entregar sin responsable")

        # ── Stock availability check before marking as preparacion ─────────────
        if target == "preparacion" and self.inventory_service is not None:
            items = self.get_order_items(order_id)
            branch_id = int(order_before.get("sucursal_id") or 1)
            for item in items:
                pid = item.get("producto_id")
                qty = float(item.get("cantidad") or 0)
                if not pid or qty <= 0:
                    continue
                try:
                    avail = self.inventory_service.get_available_stock(
                        product_id=pid, branch_id=branch_id
                    )
                    if avail is not None and avail < qty:
                        raise ValueError(
                            f"Stock insuficiente: {item.get('nombre', str(pid))} "
                            f"— disponible {avail}, requerido {qty}"
                        )
                except ValueError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "No se pudo verificar stock producto %s: %s", pid, exc
                    )

        self.repository.update_status(
            order_id,
            target,
            usuario=usuario,
            observacion=observacion,
            responsable=responsable,
            reason=f"delivery_status_{target}",
            metadata={"target_status": target, "source": "ChangeDeliveryStatusUseCase"},
            commit=False,
        )

        # Capture payment atomically with status change when delivering
        if target == "entregado" and pago_metodo:
            try:
                self.db.execute(
                    "UPDATE delivery_orders SET pago_metodo=?, pago_monto=?, fecha_entrega=datetime('now') WHERE id=?",
                    (pago_metodo, float(pago_monto), order_id),
                )
            except Exception:
                # fecha_entrega column may not exist in older schema versions
                try:
                    self.db.execute(
                        "UPDATE delivery_orders SET pago_metodo=?, pago_monto=? WHERE id=?",
                        (pago_metodo, float(pago_monto), order_id),
                    )
                except Exception:
                    pass

        order = self.repository.get_order(order_id) or {}
        if self.sale_projection is not None:
            self.sale_projection.project_status_for_order(order, target)

        folio = order.get("folio") or f"DEL-{order_id}"
        sucursal_id = int(order.get("sucursal_id") or 1)
        cliente_tel = order.get("cliente_tel") or ""
        base = {
            "_event_type": f"DELIVERY_ORDER_{target.upper()}",
            "order_id": order_id,
            "folio": folio,
            "usuario": usuario,
            "sucursal_id": sucursal_id,
            "total": order.get("total"),
        }

        events_to_publish: list[tuple[str, dict[str, Any]]] = []

        inventory_operation_id = f"delivery:{order_id}"

        if target == "cancelado":
            release_payload = {"order_id": order_id, "operation_id": inventory_operation_id, "reason": observacion or "cancelado"}
            cancelled_payload = {**base, "motivo": observacion or ""}
            self._enqueue(DeliveryEvents.INVENTORY_RELEASE_REQUIRED.value, order_id, release_payload, operation_id=release_payload["operation_id"])
            self._enqueue(DeliveryEvents.ORDER_CANCELLED.value, order_id, cancelled_payload, operation_id=f"delivery:{order_id}:cancelado")
            events_to_publish.append((DeliveryEvents.INVENTORY_RELEASE_REQUIRED.value, release_payload))
            events_to_publish.append((DeliveryEvents.ORDER_CANCELLED.value, cancelled_payload))
        if target == "preparacion":
            events_to_publish.append((DeliveryEvents.ORDER_PREPARING.value, base))
        if target == "en_ruta":
            events_to_publish.append((
                DeliveryEvents.OUT_FOR_DELIVERY.value,
                {**base, "_event_type": "DELIVERY_OUT_FOR_DELIVERY", "driver_id": order.get("driver_id"), "cliente_tel": cliente_tel},
            ))
        if target == "entregado":
            delivered_payload = {
                **base,
                "_event_type": "DELIVERY_ORDER_DELIVERED",
                "responsable": responsable,
                "driver_id": order.get("driver_id"),
            }
            self._enqueue(DeliveryEvents.ORDER_DELIVERED.value, order_id, delivered_payload, operation_id=f"delivery:{order_id}:entregado")
            events_to_publish.append((DeliveryEvents.ORDER_DELIVERED.value, delivered_payload))
            items = self.get_order_items(order_id)
            commit_payload = {
                "order_id": order_id,
                "operation_id": inventory_operation_id,
                "items": items,
                "sucursal_id": sucursal_id,
                "branch_id": sucursal_id,
            }
            self._enqueue(DeliveryEvents.INVENTORY_COMMIT_REQUIRED.value, order_id, commit_payload, operation_id=inventory_operation_id)
            events_to_publish.append((DeliveryEvents.INVENTORY_COMMIT_REQUIRED.value, commit_payload))

        notification_payload = {
            "order_id": order_id,
            "canal": "whatsapp",
            "template": target,
            "params": {"folio": folio, "status": target},
            "cliente_tel": cliente_tel,
        }
        self._enqueue(
            DeliveryEvents.CUSTOMER_NOTIFICATION_REQUESTED.value,
            order_id,
            notification_payload,
            operation_id=f"delivery:{order_id}:notify:{target}",
        )

        # Always commit the state change — outbox failures are non-fatal
        self.db.commit()
        logger.info("estado cambiado: order_id=%s estado=%s usuario=%s", order_id, target, usuario)

        for event_name, event_payload in events_to_publish:
            self.publisher(event_name, event_payload)

        self._safe_wa_notify(order, target)
        if self.whatsapp_service is not None:
            self.whatsapp_service.sync_status(str(order.get("whatsapp_order_id") or ""), target)

    def _enqueue(self, event_type: str, order_id: int, payload: dict[str, Any], operation_id: str | None = None) -> None:
        if self.outbox_repository is None:
            return
        try:
            self.outbox_repository.enqueue(
                event_type=event_type,
                aggregate_id=order_id,
                payload=payload,
                operation_id=operation_id,
                commit=False,
            )
        except Exception as exc:
            logger.exception(
                "outbox enqueue fallido event_type=%s order_id=%s — estado se commitea igual: %s",
                event_type, order_id, exc,
            )

    def _has_pending_adjustment(self, order_id: int) -> bool:
        return self.repository.has_pending_adjustment(order_id)

    def _validate_workflow_transition(self, order_id: int, target_status: str) -> None:
        order = self.repository.get_order(order_id) or {}
        workflow_type = (order.get("workflow_type") or "").strip().lower()
        delivery_type = (order.get("delivery_type") or "").strip().lower()
        scheduled_at = order.get("scheduled_at")

        if not workflow_type:
            if scheduled_at:
                workflow_type = "scheduled"
            elif delivery_type in ("pickup", "sucursal"):
                workflow_type = "counter"
            else:
                workflow_type = "delivery"

        if workflow_type == "scheduled" and target_status in ("preparacion", "en_ruta", "entregado"):
            raise ValueError("Pedido programado: primero debe activarse antes de pasar a flujo operativo.")
        if workflow_type == "counter" and target_status == "en_ruta":
            raise ValueError("Flujo mostrador no permite estado 'en_ruta'.")

    def _safe_wa_notify(self, order: dict[str, Any], status: str) -> None:
        if self.outbox_repository is not None or self.whatsapp_service is None:
            return
        ok = self.whatsapp_service.notify_status(
            phone=order.get("cliente_tel", ""),
            folio=order.get("folio") or str(order.get("id") or ""),
            status=status,
        )
        self.publisher("notificacion_whatsapp_enviada", {"order_id": order.get("id"), "status": status, "ok": bool(ok)})
