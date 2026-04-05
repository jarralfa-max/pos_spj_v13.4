# notifications/staff.py — Notificaciones internas al personal
from __future__ import annotations
from messaging.sender import send_text
from typing import List


async def notificar_nuevo_pedido_wa(phones: List[str], folio: str,
                                     cliente: str, total: float,
                                     sucursal: str):
    """Notifica al staff que llegó un pedido nuevo por WhatsApp."""
    for phone in phones:
        await send_text(phone,
            f"📱 *Nuevo pedido WhatsApp*\n\n"
            f"Folio: {folio}\n"
            f"Cliente: {cliente}\n"
            f"Total: ${total:.2f}\n"
            f"Sucursal: {sucursal}")


async def notificar_anticipo_recibido(phones: List[str], folio: str,
                                       monto: float):
    for phone in phones:
        await send_text(phone,
            f"💰 *Anticipo recibido*\n"
            f"Folio: {folio}\n"
            f"Monto: ${monto:.2f}")


async def notificar_pedido_cancelado(phones: List[str], folio: str,
                                      motivo: str = ""):
    for phone in phones:
        await send_text(phone,
            f"❌ *Pedido cancelado*\n"
            f"Folio: {folio}\n"
            f"Motivo: {motivo or 'No especificado'}")
