# middleware/handoff.py — Escalación a humano
"""
Cuando el bot no puede resolver, escala a un humano.
Notifica al staff de la sucursal correspondiente.
"""
from __future__ import annotations
import logging
from typing import Optional
from erp.bridge import ERPBridge
from messaging.sender import send_text
from notifications.staff import notificar_nuevo_pedido_wa

logger = logging.getLogger("wa.handoff")


class HandoffService:
    def __init__(self, erp: ERPBridge):
        self.erp = erp

    async def escalar(self, phone: str, sucursal_id: int,
                      motivo: str = "No se entendió el mensaje"):
        """Escala la conversación a un humano."""
        # Notificar al staff
        staff_phones = self.erp.get_staff_phones(
            sucursal_id, rol="gerente")
        if not staff_phones:
            staff_phones = self.erp.get_staff_phones(sucursal_id)

        for sp in staff_phones[:3]:
            await send_text(sp,
                f"🆘 *Atención requerida*\n\n"
                f"Cliente: {phone}\n"
                f"Motivo: {motivo}\n\n"
                f"Responde directamente al cliente desde WhatsApp.")

        await send_text(phone,
            "👤 Te estamos comunicando con un asesor.\n"
            "Responderá en unos minutos. ¡Gracias por tu paciencia!")

        logger.info("Handoff: %s → staff sucursal %d", phone, sucursal_id)
