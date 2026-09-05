# infrastructure/providers/mercadopago/gateway.py — WA-12 (§38-39)
"""
MercadoPagoGateway — implementación concreta de
`domain.whatsapp.payment_provider_ports.PaymentProviderGateway`.

**Nota de alcance, no oculta**: `flows/pago_flow.py::_generar_link_pago`
ya tiene su PROPIA llamada real a `POST /checkout/preferences` — es la
ruta en vivo hoy (§2b del runtime map de WA-0). Ese archivo no tiene
ninguna cobertura de test existente en este árbol (verificado antes de
tocarlo), así que esta fase NO lo refactoriza para compartir código —
hacerlo sin una red de pruebas real habría sido más riesgoso que el
beneficio de evitar la duplicación. Este gateway es una segunda
implementación real y probada, deliberadamente separada, candidata a
reemplazar/absorber la de `pago_flow.py` en una fase posterior con
cobertura de test para ese flujo específico primero.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from domain.whatsapp.payment_provider_ports import PaymentLinkRef

logger = logging.getLogger("wa.provider.mercadopago")

_PREFERENCES_URL = "https://api.mercadopago.com/checkout/preferences"


class MercadoPagoPreferenceError(RuntimeError):
    pass


class MercadoPagoGateway:
    def __init__(self, *, back_url_success: str = "", back_url_failure: str = "") -> None:
        self._back_url_success = back_url_success or "https://spjpos.com/pago/ok"
        self._back_url_failure = back_url_failure or "https://spjpos.com/pago/error"

    async def create_preference(
        self, *, amount: float, external_reference: str, description: str = ""
    ) -> PaymentLinkRef:
        from config.settings import MP_ACCESS_TOKEN

        if not MP_ACCESS_TOKEN:
            raise MercadoPagoPreferenceError("MP_ACCESS_TOKEN no configurado")

        expiration = (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ).strftime("%Y-%m-%dT%H:%M:%S.000-00:00")

        payload = {
            "items": [{
                "title": description or "Pedido SPJ POS",
                "quantity": 1,
                "unit_price": amount,
                "currency_id": "MXN",
            }],
            "back_urls": {"success": self._back_url_success, "failure": self._back_url_failure},
            "auto_return": "approved",
            "external_reference": external_reference,
            "expiration_date_to": expiration,
            "expires": True,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _PREFERENCES_URL, json=payload,
                headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}", "Content-Type": "application/json"},
            )

        if resp.status_code not in (200, 201):
            logger.error("MercadoPago preference falló: %s %s", resp.status_code, resp.text[:300])
            raise MercadoPagoPreferenceError(f"HTTP {resp.status_code}")

        data = resp.json()
        checkout_url = data.get("init_point", "")
        if not checkout_url:
            raise MercadoPagoPreferenceError("Respuesta sin init_point")
        return PaymentLinkRef(checkout_url=checkout_url, preference_id=str(data.get("id", "")))
