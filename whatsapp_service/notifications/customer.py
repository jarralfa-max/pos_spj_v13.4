# notifications/customer.py — Notificaciones a clientes
"""
Envía notificaciones por WhatsApp cuando cambia el estado del pedido.
Se conecta al EventBus del ERP para escuchar cambios.
"""
from __future__ import annotations
import logging
from messaging.sender import send_text
from messaging.templates import send_event_template

logger = logging.getLogger("wa.notif.customer")


async def notificar_pedido_confirmado(phone: str, folio: str, total: float):
    await send_event_template(phone, "pedido_confirmado", {
        "folio": folio, "total": f"${total:.2f}"})


async def notificar_pedido_listo(phone: str, folio: str):
    await send_event_template(phone, "pedido_listo", {"folio": folio})


async def notificar_anticipo_requerido(phone: str, folio: str,
                                        monto: float, link_pago: str = ""):
    await send_event_template(phone, "anticipo_requerido", {
        "folio": folio, "monto": f"${monto:.2f}",
        "link_pago": link_pago or "Contacta la sucursal"})


async def notificar_pago_recibido(phone: str, folio: str, monto: float):
    await send_event_template(phone, "pago_recibido", {
        "folio": folio, "monto": f"${monto:.2f}"})


async def notificar_en_camino(phone: str, folio: str):
    await send_event_template(phone, "entrega_en_camino", {"folio": folio})


async def notificar_recordatorio_anticipo(phone: str, folio: str,
                                           fecha_entrega: str):
    await send_event_template(phone, "recordatorio_anticipo", {
        "folio": folio, "fecha_entrega": fecha_entrega})
