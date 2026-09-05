# domain/whatsapp/consent_ports.py — WA-14 (§44 del prompt maestro)
"""
ConsentApiClient — WhatsApp NUNCA decide ni almacena consentimiento por su
cuenta; solo lee/escribe a través de este puerto, que envuelve el dominio
REAL de Customer Privacy (CRM-9,
`backend/domain/customer_privacy/entities/customer_consent.py` +
`customer_consents`, tabla ya en producción) — mismo criterio de "no
inventar un segundo modelo" que `erp_ports.py` (WA-9) aplicó a
Customers/Orders/Quotes/Payments/Delivery.

CRM-9 construyó el dominio completo pero, según su propio comentario en
`messaging/sender.py::_is_whatsapp_opted_out` (CRM-31), **nunca tuvo un
productor real de estos registros** — WA-14 es el primero. `ConsentType.WHATSAPP`
es el tipo de consentimiento que ya lee `_is_whatsapp_opted_out` antes de
cada envío; WA-14 completa el otro lado (quién escribe esos registros).
"""
from __future__ import annotations

from typing import Optional, Protocol


class ConsentApiClient(Protocol):
    async def get_status(self, customer_id: str) -> Optional[str]:
        """Estado efectivo (`ConsentStatus.value`) del consentimiento
        WHATSAPP más reciente de este cliente, o `None` si nunca se
        capturó ninguno — nunca se infiere un valor por defecto (§44)."""
        ...

    async def grant(self, customer_id: str, *, evidence_reference: str) -> None:
        """Registra un consentimiento WHATSAPP otorgado explícitamente
        (`evidence_reference` es obligatorio — nunca se infiere)."""
        ...

    async def opt_out(self, customer_id: str, *, reason: str) -> None:
        """Registra que el cliente retiró (o rechazó, si nunca lo había
        otorgado) su consentimiento WHATSAPP."""
        ...
