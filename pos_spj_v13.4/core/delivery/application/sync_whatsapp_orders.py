from __future__ import annotations

import logging

from core.delivery.domain.events import DeliveryEvents

from .ports import EventPublisher, NoopPublisher

logger = logging.getLogger("spj.delivery.application.sync_whatsapp")


class SyncWhatsAppOrdersUseCase:
    def __init__(self, *, db, repository, whatsapp_service=None, publisher: EventPublisher = NoopPublisher) -> None:
        self.db = db
        self.repository = repository
        self.whatsapp_service = whatsapp_service
        self.publisher = publisher

    def pull_orders_from_whatsapp(self) -> None:
        pulled = False
        if self.whatsapp_service is not None:
            for item in self.whatsapp_service.pull_orders():
                try:
                    oid = self.repository.upsert_order_from_whatsapp(item)
                    self.publisher(
                        DeliveryEvents.ORDER_CREATED.value,
                        {"order_id": oid, "payload": item, "source_channel": "whatsapp", "canal": "whatsapp"},
                    )
                    items = item.get("items") or []
                    if items:
                        self.publisher(
                            DeliveryEvents.ORDER_RESERVED.value,
                            {
                                "order_id": oid,
                                "operation_id": f"delivery:{oid}",
                                "items": items,
                                "branch_id": item.get("sucursal_id", 1),
                            },
                        )
                    pulled = True
                except Exception as exc:
                    logger.warning("pull_orders_from_whatsapp upsert failed: %s", exc)
        if not pulled:
            self.sync_pending_sales_to_delivery_orders()

    def sync_pending_sales_to_delivery_orders(self) -> int:
        imported = 0
        try:
            sales = self.repository.iter_pending_whatsapp_sales(limit=200)
        except Exception as exc:
            logger.warning("sync_pending_sales_to_delivery_orders query failed: %s", exc)
            return 0

        for data in sales:
            venta_id = data.get("id")
            if not venta_id:
                continue
            payload = {
                "id": venta_id,
                "venta_id": venta_id,
                "folio": data.get("folio") or data.get("codigo"),
                "cliente_id": data.get("cliente_id"),
                "cliente_nombre": data.get("cliente_nombre") or data.get("cliente"),
                "cliente_tel": data.get("cliente_tel") or data.get("telefono") or data.get("cliente_telefono"),
                "direccion": data.get("direccion") or data.get("direccion_entrega"),
                "total": data.get("total") or 0,
                "sucursal_id": data.get("sucursal_id") or 1,
                "delivery_type": data.get("delivery_type") or data.get("tipo_entrega"),
                "workflow_type": data.get("workflow_type"),
                "scheduled_at": data.get("scheduled_at") or data.get("fecha_entrega_programada"),
                "items": data.get("items") or [],
                "source_channel": "whatsapp",
            }
            try:
                oid = self.repository.upsert_order_from_whatsapp(payload, usuario="sync_local_ventas")
                items = payload.get("items") or []
                if items:
                    self.publisher(
                        DeliveryEvents.ORDER_RESERVED.value,
                        {
                            "order_id": oid,
                            "operation_id": f"delivery:{oid}",
                            "items": items,
                            "branch_id": payload.get("sucursal_id", 1),
                        },
                    )
                imported += 1
            except Exception as exc:
                logger.warning("sync_pending_sales_to_delivery_orders upsert failed venta_id=%s: %s", venta_id, exc)
        return imported
