# webhook/mercadopago.py — Webhook de confirmación de pago MercadoPago
"""
Recibe notificaciones de pago y actualiza el estado del pedido.

SDLC-WA-001: el pago se casa por la venta de `external_reference`
(`<venta_id>:<teléfono>`), su teléfono, la moneda y el monto exacto del total.
Lo que no casa queda en `whatsapp_unmatched_payments`. Un pago se aplica una
sola vez por su id de MercadoPago, y el cliente sólo recibe aviso después del
match. Si no se pudo guardar nada, se responde 5xx para que el proveedor
reintente.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from whatsapp_service.domain.money import loads_decimal
from whatsapp_service.domain.money import to_decimal
import logging
from fastapi import APIRouter, Query, Request, Response
from backend.shared.ids import new_uuid
from whatsapp_service.middleware.hmac_validator import verify_mp_signature
from whatsapp_service.state.business_idempotency import BusinessIdempotencyService

logger = logging.getLogger("wa.webhook.mp")
router = APIRouter()

MAX_BODY_BYTES = 64 * 1024
_PAYMENT_ACTIONS = frozenset({"payment.created", "payment.updated"})
_EXPECTED_CURRENCY = "MXN"
_CENTS = Decimal("0.01")

_erp_bridge = None
_events = None


def init_mp_webhook(erp_bridge, events):
    global _erp_bridge, _events
    _erp_bridge = erp_bridge
    _events = events


@router.post("/webhook/mercadopago")
async def mp_notification(
    request: Request,
    data_id: str = Query(None, alias="data.id"),
):
    """Recibe notificación de pago de MercadoPago."""
    from whatsapp_service.config.settings import (
        allow_unsigned_webhooks,
        get_mp_signature_max_age_seconds,
        get_mp_webhook_secret,
        unsigned_webhook_rejection,
    )

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        logger.warning("Notificación MercadoPago rechazada: cuerpo de %d bytes", len(body))
        return Response(status_code=413)
    secret = get_mp_webhook_secret()
    if secret:
        x_signature = request.headers.get("x-signature", "")
        x_request_id = request.headers.get("x-request-id", "")
        if not verify_mp_signature(
            x_signature, x_request_id, data_id, secret,
            max_age_seconds=get_mp_signature_max_age_seconds(),
        ):
            client_host = request.client.host if request.client else "?"
            logger.warning("Notificación MercadoPago rechazada desde %s", client_host)
            return Response(status_code=403)
    elif allow_unsigned_webhooks():
        logger.warning(
            "MP_WEBHOOK_SECRET no configurado; notificación de MercadoPago "
            "aceptada sin firma por WA_ALLOW_UNSIGNED_WEBHOOKS (sólo máquina "
            "de desarrollo)."
        )
    else:
        # WA-1 / S4, SDLC-WA-002: sin MP_WEBHOOK_SECRET no hay forma de
        # verificar la notificación de pago. Fail-closed en cualquier entorno
        # salvo el opt-in explícito de arriba.
        logger.error(unsigned_webhook_rejection("MP_WEBHOOK_SECRET"))
        return Response(status_code=503)

    try:
        data = loads_decimal(body) if body else {}
    except Exception:
        logger.warning("Notificación MercadoPago con JSON inválido")
        return Response(status_code=400)
    if not isinstance(data, dict):
        return Response(status_code=400)

    if data.get("action", "") not in _PAYMENT_ACTIONS:
        return {"status": "ok"}

    body_id = str((data.get("data") or {}).get("id") or "").strip()
    query_id = str(data_id or "").strip()
    if query_id and body_id and query_id != body_id:
        logger.warning("Notificación MercadoPago con ids distintos en URL y cuerpo")
        return Response(status_code=400)
    payment_id = query_id or body_id
    if not payment_id:
        return {"status": "ok"}

    from whatsapp_service.config.settings import MP_ACCESS_TOKEN
    if not MP_ACCESS_TOKEN or _erp_bridge is None:
        logger.error(
            "Pago MercadoPago %s sin procesar: falta MP_ACCESS_TOKEN o la conexión "
            "al ERP; se pide reintento.", payment_id)
        return Response(status_code=503)

    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.mercadopago.com/v1/payments/{payment_id}",
                headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"})
        if resp.status_code != 200:
            logger.error("Consulta del pago MercadoPago %s respondió %s",
                         payment_id, resp.status_code)
            return Response(status_code=502)
        payment = loads_decimal(resp.content)
    except Exception:
        logger.exception("Consulta del pago MercadoPago %s falló", payment_id)
        return Response(status_code=502)

    if payment.get("status", "") != "approved":
        logger.info("Pago MercadoPago %s en estado %s; nada que aplicar",
                    payment_id, payment.get("status", ""))
        return {"status": "ok"}

    try:
        applied = _settle_approved_payment(payment_id, payment)
    except _RetryLater:
        return Response(status_code=503)
    except Exception:
        logger.exception("Error aplicando el pago MercadoPago %s", payment_id)
        return Response(status_code=500)

    if applied:
        phone, amount = applied
        try:
            from whatsapp_service.notifications import customer
            await customer.notificar_pago_recibido(phone, f"MP-{payment_id}", amount)
        except Exception:
            logger.exception("Pago MercadoPago %s aplicado; falló el aviso al cliente",
                             payment_id)

    return {"status": "ok"}


class _RetryLater(Exception):
    """Otro intento del mismo pago sigue en curso."""


def _digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _match_sale(external_ref: str, amount: Decimal, currency: str):
    """Devuelve `(venta, None)` si el pago casa, o `(None, motivo)`."""
    sale_ref, separator, ref_phone = str(external_ref or "").partition(":")
    sale_ref = sale_ref.strip()
    if not separator or not sale_ref:
        return None, "referencia sin venta"
    row = _erp_bridge.db.execute(
        "SELECT v.id, v.folio, v.total, v.estado, c.telefono FROM ventas v "
        "LEFT JOIN clientes c ON c.id = v.cliente_id WHERE v.id = ?",
        (sale_ref,),
    ).fetchone()
    if row is None:
        return None, "venta no encontrada"
    sale_id, folio, total, estado, sale_phone = row[0], row[1], row[2], row[3], row[4]
    if estado != "pendiente_wa":
        return None, f"venta no pendiente ({estado})"
    phone_digits = _digits(ref_phone)[-10:]
    if not phone_digits or phone_digits != _digits(sale_phone)[-10:]:
        return None, "teléfono no coincide"
    if currency != _EXPECTED_CURRENCY:
        return None, f"moneda no esperada ({currency})"
    expected = to_decimal(total).quantize(_CENTS)
    if amount != expected:
        return None, f"monto no coincide (esperado {expected}, recibido {amount})"
    return {"venta_id": sale_id, "folio": folio or "", "telefono": ref_phone.strip()}, None


def _record_unmatched(payment_id: str, payment: dict, amount: Decimal, reason: str) -> None:
    _erp_bridge.db.execute(
        "INSERT OR IGNORE INTO whatsapp_unmatched_payments "
        "(id, provider, provider_payment_id, external_reference, amount, currency, "
        "provider_status, reason, created_at) VALUES (?, 'MERCADOPAGO', ?, ?, ?, ?, ?, ?, ?)",
        (
            new_uuid(), payment_id, str(payment.get("external_reference") or ""),
            str(amount), str(payment.get("currency_id") or ""),
            str(payment.get("status") or ""), reason,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    _erp_bridge.db.commit()
    logger.warning("Pago MercadoPago %s sin asignar: %s", payment_id, reason)


def _settle_approved_payment(payment_id: str, payment: dict):
    """Aplica un pago aprobado. Devuelve `(teléfono, monto)` sólo la primera vez
    que se aplica; `None` si ya estaba aplicado o quedó en la bandeja."""
    amount = to_decimal(payment.get("transaction_amount")).quantize(_CENTS)
    idem = BusinessIdempotencyService(_erp_bridge.db)
    action_key = f"mp_payment:{payment_id}"
    previous = idem.get(action_key)
    if previous is not None:
        if previous.status == "completed":
            return None
        if previous.status == "failed":
            _record_unmatched(payment_id, payment, amount,
                              "confirmación falló en un intento anterior")
            return None
        raise _RetryLater()

    sale, reason = _match_sale(
        payment.get("external_reference", ""), amount, str(payment.get("currency_id") or ""))
    if reason:
        _record_unmatched(payment_id, payment, amount, reason)
        return None

    applied = {}

    def _confirm_payment() -> dict:
        confirmed = _erp_bridge.confirmar_pago_anticipo(
            venta_id=sale["venta_id"],
            monto=amount,
            referencia=f"MP-{payment_id}",
            metodo="mercadopago",
        )
        if not confirmed:
            raise RuntimeError(f"el ERP no confirmó la venta {sale['venta_id']}")
        if _events:
            from whatsapp_service.erp.events import WA_ANTICIPO_PAGADO, PAYMENT_RECEIVED
            _events.emit(PAYMENT_RECEIVED, {
                "venta_id": sale["venta_id"],
                "folio": sale["folio"],
                "monto": amount,
                "metodo": "mercadopago",
                "referencia": payment_id,
                "telefono": sale["telefono"],
            })
            _events.emit(WA_ANTICIPO_PAGADO, {
                "payment_id": payment_id,
                "monto": amount,
                "telefono": sale["telefono"],
                "folio": sale["folio"],
            })
        applied["result"] = (sale["telefono"], amount)
        return {"venta_id": sale["venta_id"], "payment_id": payment_id, "monto": amount}

    outcome = idem.run_once(
        action_key=action_key,
        phone=sale["telefono"],
        action_type="confirm_payment",
        callback=_confirm_payment,
    )
    if "result" in applied:
        return applied["result"]
    if outcome.get("idempotency_status") == "completed":
        return None
    raise _RetryLater()
