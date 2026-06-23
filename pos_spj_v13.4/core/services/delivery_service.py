from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from repositories.delivery_repository import DeliveryRepository
from core.services.delivery_whatsapp_service import DeliveryWhatsAppService
from core.services.geocoding_service import GeocodingService
from core.delivery.application.delivery_total_service import DeliveryTotalService
from core.delivery.domain.state_machine import DeliveryStateMachine
from core.delivery.infrastructure.whatsapp_delivery_notifier import WhatsAppDeliveryNotifier
from core.events.event_bus import get_bus
from core.delivery.infrastructure.delivery_outbox_repository import DeliveryOutboxRepository
from core.delivery.infrastructure.delivery_schema_migrator import DeliverySchemaMigrator
from core.delivery.projections.sale_delivery_projection import SaleDeliveryProjectionService
from core.delivery.application.activate_scheduled_order import ActivateScheduledOrderUseCase
from core.delivery.application.adjust_delivery_weight import AdjustDeliveryWeightUseCase
from core.delivery.application.assign_delivery_driver import AssignDeliveryDriverUseCase
from core.delivery.application.cancel_delivery_order import CancelDeliveryOrderUseCase
from core.delivery.application.change_delivery_status import ChangeDeliveryStatusUseCase
from core.services.inventory_balance_service import InventoryBalanceService
from core.delivery.application.create_delivery_order import CreateDeliveryOrderUseCase
from core.delivery.application.sync_whatsapp_orders import SyncWhatsAppOrdersUseCase

logger = logging.getLogger("spj.services.delivery")


class DeliveryService:
    """Application service facade for the delivery bounded context.

    All mutations delegate to application use cases. Reads delegate to
    the repository or query services. No business logic lives here.
    """
    def __init__(
        self,
        db,
        repository: Optional[DeliveryRepository] = None,
        whatsapp_service: Optional[DeliveryWhatsAppService] = None,
        geocoding_service: Optional[GeocodingService] = None,
    ):
        self.db = db
        self.repository = repository or DeliveryRepository(db)
        self.whatsapp_service = whatsapp_service or DeliveryWhatsAppService()
        self.geocoding_service = geocoding_service or GeocodingService()
        self.order_total_service = DeliveryTotalService(self.repository)
        self.sale_projection = SaleDeliveryProjectionService(db) if db is not None else None
        self.outbox_repository = DeliveryOutboxRepository(db) if db is not None else None
        self._ensure_adjustment_columns()

    def _ensure_adjustment_columns(self) -> None:
        """Deprecated compatibility shim; schema changes live in DeliverySchemaMigrator."""
        if self.db is None:
            return
        DeliverySchemaMigrator(self.db).ensure_schema()

    def list_orders(self, estado: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.repository.list_orders(estado=estado)

    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Legacy convenience accessor; repository remains the owner of reads."""
        return self.repository.get_order(order_id)

    _UI_ACTION_METADATA: Dict[str, Dict[str, str]] = {
        "preparacion": {"icon": "👨‍🍳", "label": "Enviar a preparación", "style": "primary"},
        "cancelado": {"icon": "✖", "label": "Cancelar pedido", "style": "danger"},
        "ver_detalle": {"icon": "🔍", "label": "Ver detalle", "style": "secondary"},
        "ajustar_peso": {"icon": "⚖️", "label": "Ajustar peso", "style": "warning"},
        "en_ruta": {"icon": "🛵", "label": "Enviar a ruta", "style": "primary"},
        "asignar": {"icon": "👤", "label": "Asignar repartidor", "style": "primary"},
        "entregado": {"icon": "✅", "label": "Marcar entregado", "style": "success"},
        "notificar_wa": {"icon": "📲", "label": "Notificar por WA", "style": "secondary"},
        "imprimir": {"icon": "🖨️", "label": "Imprimir ticket", "style": "secondary"},
        "reactivar": {"icon": "♻️", "label": "Reactivar pedido", "style": "warning"},
        "activar_programado": {"icon": "▶", "label": "Activar ahora", "style": "success"},
        "reprogramar": {"icon": "🗓️", "label": "Reprogramar", "style": "warning"},
        "ver_forecast": {"icon": "📈", "label": "Ver forecast", "style": "secondary"},
    }

    def get_valid_actions(
        self,
        *,
        status: str,
        workflow_type: str = "",
        adjustment_pending: bool = False,
        scheduled_at: Optional[str] = None,
        delivery_type: str = "",
    ) -> List[Dict[str, str]]:
        """Return valid UI actions for an order context.

        The action keys come from ``DeliveryStateMachine`` so widgets/PWA views
        do not duplicate workflow rules. This facade only adds UI metadata
        (icon, label and style) and non-transition read actions.
        """
        order_context = {
            "estado": status,
            "workflow_type": workflow_type,
            "delivery_type": delivery_type,
            "scheduled_at": scheduled_at,
            "adjustment_pending": adjustment_pending,
        }
        action_keys = DeliveryStateMachine().get_valid_actions(order_context)
        if (status or "").strip().lower() in {"programado", "scheduled"} and "ver_forecast" not in action_keys:
            action_keys.insert(2, "ver_forecast")
        if (status or "").strip().lower() == "pendiente" and "ver_detalle" not in action_keys:
            action_keys.append("ver_detalle")
        return [
            {
                "key": key,
                "icon": self._UI_ACTION_METADATA.get(key, {}).get("icon", ""),
                "label": self._UI_ACTION_METADATA.get(key, {}).get("label", key),
                "style": self._UI_ACTION_METADATA.get(key, {}).get("style", "secondary"),
            }
            for key in action_keys
        ]

    def _create_order_use_case(self) -> CreateDeliveryOrderUseCase:
        return CreateDeliveryOrderUseCase(
            db=self.db,
            repository=self.repository,
            geocoding_service=self.geocoding_service,
            whatsapp_service=self.whatsapp_service,
            publisher=self._publish,
            outbox_repository=self.outbox_repository,
        )

    def create_order(self, data: Dict[str, Any], usuario: str = "sistema") -> int:
        return self._create_order_use_case().execute(data, usuario=usuario)

    def _has_pending_adjustment(self, order_id: int) -> bool:
        try:
            return self.repository.has_pending_adjustment(order_id)
        except Exception as exc:
            logger.warning("No se pudo validar ajuste pendiente delivery order=%s: %s", order_id, exc)
            return False

    def assign_driver(
        self,
        order_id: int,
        driver_id: int,
        tiempo_estimado: str = "",
        notas: str = "",
        usuario: str = "sistema",
    ) -> dict:
        """Assign driver and atomically transition order to 'preparacion'."""
        return AssignDeliveryDriverUseCase(
            db=self.db,
            repository=self.repository,
            publisher=self._publish,
            outbox_repository=self.outbox_repository,
        ).execute(
            order_id=order_id,
            driver_id=driver_id,
            tiempo_estimado=tiempo_estimado,
            notas=notas,
            usuario=usuario,
        )

    def _change_status_use_case(self) -> ChangeDeliveryStatusUseCase:
        return ChangeDeliveryStatusUseCase(
            db=self.db,
            repository=self.repository,
            sale_projection=self.sale_projection,
            whatsapp_service=self.whatsapp_service,
            publisher=self._publish,
            get_order_items=self.get_order_items,
            outbox_repository=self.outbox_repository,
            inventory_service=InventoryBalanceService(self.db) if self.db is not None else None,
            credit_service=self._credit_service(),
            print_coordinator=self._print_coordinator(),
        )

    def _print_coordinator(self):
        """Canonical auto-print coordinator. Returns None if unavailable."""
        if self.db is None:
            return None
        try:
            from core.delivery.application.print_coordinator import DeliveryPrintCoordinator
            return DeliveryPrintCoordinator(self.db)
        except Exception as exc:
            logger.debug("DeliveryPrintCoordinator unavailable: %s", exc)
            return None

    def _credit_service(self):
        """Canonical customer-credit gate. Returns None if unavailable."""
        if self.db is None:
            return None
        try:
            from application.services.customer_credit_service import CustomerCreditService
            return CustomerCreditService(self.db)
        except Exception as exc:
            logger.debug("CustomerCreditService unavailable: %s", exc)
            return None

    def update_status(
        self,
        order_id: int,
        status: str,
        usuario: str,
        responsable: str = "",
        observacion: str = "",
        pago_metodo: str = "",
        pago_monto: float = 0.0,
    ) -> None:
        return self._change_status_use_case().execute(
            order_id,
            status,
            usuario=usuario,
            responsable=responsable,
            observacion=observacion,
            pago_metodo=pago_metodo,
            pago_monto=pago_monto,
        )

    def activate_scheduled_order(self, order_id: int, usuario: str = "sistema") -> Dict[str, Any]:
        return ActivateScheduledOrderUseCase(
            db=self.db,
            repository=self.repository,
            sale_projection=self.sale_projection,
            publisher=self._publish,
        ).execute(order_id, usuario=usuario)

    def cancel_order(self, order_id: int, usuario: str = "sistema", motivo: str = "") -> Dict[str, Any]:
        return CancelDeliveryOrderUseCase(self._change_status_use_case()).execute(
            order_id, usuario=usuario, motivo=motivo
        )

    def _recalculate_order_total(self, order_id: int) -> float:
        return self.order_total_service.recalculate_order_total(order_id, commit=False)

    def _adjust_reservation(self, operation_id: str, product_id, new_qty: float, branch_id) -> int:
        """Re-set the inventory soft-lock to the real prepared quantity.

        Canonical route: ReservationService.adjust_reservation. Idempotent.
        """
        from core.services.reservation_service import ReservationService
        return ReservationService().adjust_reservation(
            self.db, operation_id, product_id, float(new_qty), str(branch_id or "")
        )

    def _sync_venta_total(self, order_id: int, new_total: float) -> None:
        try:
            order = self.repository.get_order(order_id) or {}
            venta_id = order.get("venta_id")
            if venta_id and self.sale_projection is not None:
                self.sale_projection.project_total(venta_id, new_total)
        except Exception as exc:
            logger.debug("_sync_venta_total: %s", exc)

    def _notify_adjustment_pending(self, order: Dict[str, Any], item_name: str, requested_qty: float,
                                   prepared_qty: float, unit: str, new_subtotal: float,
                                   diff_qty: float) -> bool:
        phone = order.get("cliente_tel") or ""
        if not phone:
            return False
        folio = order.get("folio") or f"DEL-{order.get('id','')}"
        try:
            return WhatsAppDeliveryNotifier().notify_adjustment_required(
                phone=phone,
                folio=folio,
                item_name=item_name,
                requested_qty=requested_qty,
                prepared_qty=prepared_qty,
                unit=unit,
                new_subtotal=new_subtotal,
                diff_qty=diff_qty,
            )
        except Exception as exc:
            logger.warning("No se pudo notificar ajuste pendiente por WhatsApp: %s", exc)
            return False

    def adjust_item_weight(
        self,
        order_id: int,
        item_id: int,
        prepared_qty: float,
        prepared_by: str,
        adjustment_reason: str = "",
        unit: str = "",
    ) -> Dict[str, Any]:
        return AdjustDeliveryWeightUseCase(
            db=self.db,
            repository=self.repository,
            publisher=self._publish,
            notify_adjustment_pending=self._notify_adjustment_pending,
            recalculate_order_total=self._recalculate_order_total,
            sync_sale_total=self._sync_venta_total,
            outbox_repository=self.outbox_repository,
            adjust_reservation=self._adjust_reservation,
        ).execute(
            order_id=order_id,
            item_id=item_id,
            prepared_qty=prepared_qty,
            prepared_by=prepared_by,
            adjustment_reason=adjustment_reason,
            unit=unit,
        )

    def get_order_items(self, order_id) -> List[Dict[str, Any]]:
        """Return delivery items with units resolved from productos table.

        The unit column in delivery_items may store a legacy default ("kg") that
        does not reflect the product's actual configured unit. We LEFT JOIN
        productos so the product's unit takes precedence; delivery_items.unidad
        is only used as fallback when the product row is missing.
        """
        try:
            rows = self.db.execute(
                """SELECT i.id, i.nombre, i.cantidad, i.precio_unitario, i.subtotal,
                          COALESCE(p.unidad, i.unidad, '') AS unidad,
                          i.producto_id, i.requested_qty, i.prepared_qty, i.final_qty,
                          i.prepared_by, i.prepared_at, i.adjustment_reason, i.tolerance_exceeded,
                          i.pending_prepared_qty, i.pending_subtotal, i.adjustment_status,
                          i.adjustment_requested_at, i.adjustment_responded_at, i.adjustment_response,
                          i.tolerance_units
                   FROM delivery_items i
                   LEFT JOIN productos p ON p.id = i.producto_id
                   WHERE i.delivery_id=? ORDER BY i.id""",
                (order_id,),
            ).fetchall()
        except Exception:
            # Fallback without join if productos table is absent.
            try:
                rows = self.db.execute(
                    """SELECT id, nombre, cantidad, precio_unitario, subtotal, unidad,
                              producto_id, requested_qty, prepared_qty, final_qty,
                              prepared_by, prepared_at, adjustment_reason, tolerance_exceeded,
                              pending_prepared_qty, pending_subtotal, adjustment_status,
                              adjustment_requested_at, adjustment_responded_at, adjustment_response,
                              tolerance_units
                       FROM delivery_items WHERE delivery_id=? ORDER BY id""",
                    (order_id,),
                ).fetchall()
            except Exception as exc:
                logger.debug("get_order_items error: %s", exc)
                return []
        cols = ["id", "nombre", "cantidad", "precio_unitario", "subtotal", "unidad",
                "producto_id", "requested_qty", "prepared_qty", "final_qty",
                "prepared_by", "prepared_at", "adjustment_reason", "tolerance_exceeded",
                "pending_prepared_qty", "pending_subtotal", "adjustment_status",
                "adjustment_requested_at", "adjustment_responded_at", "adjustment_response",
                "tolerance_units"]
        if rows and hasattr(rows[0], "keys"):
            items = [dict(r) for r in rows]
        else:
            items = [dict(zip(cols, r)) for r in rows]
        # Secondary resolution: when producto_id is NULL (WhatsApp-sourced items),
        # the JOIN returned no product row. Look up by item name in productos so the
        # product's configured unit replaces whatever legacy default is in unidad.
        for item in items:
            if item.get("producto_id"):
                continue
            nombre = (item.get("nombre") or "").strip()
            if not nombre:
                continue
            try:
                row = self.db.execute(
                    "SELECT unidad FROM productos WHERE nombre=? AND activo=1 LIMIT 1",
                    (nombre,),
                ).fetchone()
                if row:
                    unit = row[0] if not hasattr(row, "keys") else row["unidad"]
                    if unit:
                        item["unidad"] = unit
            except Exception:
                pass
        return items

    def autocomplete_address(self, query: str):
        return self.geocoding_service.autocomplete(query)

    def pull_orders_from_whatsapp(self) -> None:
        return SyncWhatsAppOrdersUseCase(
            db=self.db,
            repository=self.repository,
            whatsapp_service=self.whatsapp_service,
            publisher=self._publish,
        ).pull_orders_from_whatsapp()

    def _publish(self, event: str, payload: Dict[str, Any]) -> None:
        try:
            get_bus().publish(event, payload)
        except Exception as exc:
            logger.warning("DeliveryService._publish failed event=%s: %s", event, exc)
