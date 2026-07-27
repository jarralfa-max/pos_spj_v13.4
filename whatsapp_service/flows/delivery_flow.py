# flows/delivery_flow.py — Integración con módulo delivery del ERP
"""
Envía datos de entrega al módulo delivery existente.
No duplica lógica — solo conecta el pedido WA con delivery.
"""
from __future__ import annotations
import logging
from erp.bridge import ERPBridge
from erp.events import WAEventEmitter
from messaging.sender import send_text

logger = logging.getLogger("wa.delivery")


class DeliveryBridge:
    """Conecta pedidos de WhatsApp con el módulo delivery del ERP."""

    def __init__(self, erp: ERPBridge, events: WAEventEmitter):
        self.erp = erp
        self.events = events

    async def crear_entrega(self, venta_id: int, direccion: str,
                            sucursal_id: int, cliente_phone: str,
                            notas: str = "") -> bool:
        """Registra una entrega a domicilio en el ERP.

        Delegates to DeliveryGateway.schedule() so that the canonical
        delivery_repository / SyncWhatsAppOrdersUseCase path remains the
        single source of truth for delivery_orders rows.
        """
        try:
            ok = self.erp.delivery.schedule(
                venta_id=venta_id,
                direccion=direccion,
                fecha_entrega="",
                telefono_cliente=cliente_phone,
            )
            if ok:
                self.events.emit("WA_DELIVERY_CREADO", {
                    "venta_id": venta_id,
                    "direccion": direccion,
                    "telefono": cliente_phone,
                }, sucursal_id=sucursal_id, prioridad=3)
                logger.info("Delivery registrado via gateway: venta=%d, suc=%d", venta_id, sucursal_id)
            return ok
        except Exception as e:
            logger.error("Error creando delivery: %s", e)
            return False

    async def notificar_en_camino(self, venta_id: int, phone: str):
        """Notifica al cliente que su pedido va en camino."""
        await send_text(phone,
            "🛵 *¡Tu pedido va en camino!*\n"
            "El repartidor está en ruta hacia tu dirección.")

    async def notificar_entregado(self, venta_id: int, phone: str):
        """Notifica al cliente que se entregó."""
        await send_text(phone,
            "✅ *Pedido entregado*\n"
            "¡Gracias por tu compra! 😊")
