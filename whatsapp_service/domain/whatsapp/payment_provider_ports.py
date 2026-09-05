# domain/whatsapp/payment_provider_ports.py — WA-12 (§38-39 del prompt maestro)
"""
Puerto del proveedor de pagos (MercadoPago) — separado deliberadamente de
`erp_ports.py::PaymentsApiClient` (WA-9). Son dos sistemas externos
distintos: `PaymentsApiClient` habla con el ERP (registrar/confirmar un
anticipo en `anticipos`/`ventas`); este puerto habla con MercadoPago
(generar el link de pago real). Mismo criterio de separación que
`WhatsAppProviderGateway` (mensajería, WA-5) vs `erp_ports.py` (ERP,
WA-9) — un proveedor externo, un puerto propio.

§39 es explícito: el webhook financiero (MercadoPago) pertenece al
bounded context Payments, no a WhatsApp — WhatsApp puede solicitar un
link, enviarlo, y comunicar la confirmación, pero no es dueño de ese
webhook. Este puerto cubre solo la parte que SÍ es del canal: pedir que
se genere un link para poder mandarlo por chat.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PaymentLinkRef:
    checkout_url: str
    preference_id: str = ""


class PaymentProviderGateway(Protocol):
    async def create_preference(
        self, *, amount: float, external_reference: str, description: str = ""
    ) -> PaymentLinkRef: ...
