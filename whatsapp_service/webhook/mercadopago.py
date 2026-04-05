# webhook/mercadopago.py — Webhook de confirmación de pago MercadoPago
"""
Recibe notificaciones de pago y actualiza el estado del pedido.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Request

logger = logging.getLogger("wa.webhook.mp")
router = APIRouter()

_erp_bridge = None
_events = None


def init_mp_webhook(erp_bridge, events):
    global _erp_bridge, _events
    _erp_bridge = erp_bridge
    _events = events


@router.post("/webhook/mercadopago")
async def mp_notification(request: Request):
    """Recibe notificación de pago de MercadoPago."""
    try:
        data = await request.json()
    except Exception:
        return {"status": "error"}

    action = data.get("action", "")
    if action != "payment.created":
        return {"status": "ok"}

    try:
        payment_data = data.get("data", {})
        payment_id = payment_data.get("id")

        if not payment_id:
            return {"status": "ok"}

        # Consultar detalles del pago a MP API
        import httpx
        from config.settings import MP_ACCESS_TOKEN
        if not MP_ACCESS_TOKEN:
            return {"status": "ok"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.mercadopago.com/v1/payments/{payment_id}",
                headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"})

        if resp.status_code != 200:
            return {"status": "error"}

        payment = resp.json()
        status = payment.get("status", "")
        external_ref = payment.get("external_reference", "")  # phone del cliente
        amount = payment.get("transaction_amount", 0)

        if status == "approved" and external_ref and _erp_bridge:
            logger.info("Pago aprobado: %s, monto=%s, ref=%s",
                         payment_id, amount, external_ref)

            # Notificar al cliente
            from notifications.customer import notificar_pago_recibido
            await notificar_pago_recibido(
                external_ref, f"MP-{payment_id}", amount)

            if _events:
                from erp.events import WA_ANTICIPO_PAGADO
                _events.emit(WA_ANTICIPO_PAGADO, {
                    "payment_id": payment_id,
                    "monto": amount,
                    "telefono": external_ref,
                })

    except Exception as e:
        logger.error("Error procesando pago MP: %s", e)

    return {"status": "ok"}
