# infrastructure/erp_clients/consent_client.py — WA-14
"""
CustomerConsentApiClient — adaptador real de `ConsentApiClient`
(`domain/whatsapp/consent_ports.py`) envolviendo el
`CustomerConsentRepository` REAL de Customer Privacy (CRM-9), contra la
MISMA conexión SQLite que ya usa el resto del `CompositionRoot` (WA-4) —
ninguna conexión nueva, mismo criterio que el resto de WA-9/WA-13.

`CustomerConsentRepository` (CRM-9) nunca hace commit por diseño propio
("Repositories never commit; the UnitOfWork owns it") — este adaptador SÍ
comitea explícitamente después de cada escritura, mismo patrón que todos
los `Sqlite*Repository` de este árbol (`infrastructure/persistence/`), ya
que aquí no existe ningún `UnitOfWork` de Customer Privacy en juego.
"""
from __future__ import annotations

from typing import Optional

from backend.domain.customer_privacy.entities.customer_consent import CustomerConsent
from backend.domain.customer_privacy.enums import ConsentChannel, ConsentStatus, ConsentType
from backend.infrastructure.db.repositories.customer_privacy.customer_consent_repository import (
    CustomerConsentRepository,
)

_WHATSAPP = ConsentType.WHATSAPP.value


class CustomerConsentApiClient:
    def __init__(self, conn) -> None:
        self._conn = conn
        self._repo = CustomerConsentRepository(conn)

    async def get_status(self, customer_id: str) -> Optional[str]:
        consent = self._repo.get_latest(customer_id, _WHATSAPP)
        return consent.effective_status().value if consent else None

    async def grant(self, customer_id: str, *, evidence_reference: str) -> None:
        consent = CustomerConsent.capture(
            customer_id, ConsentType.WHATSAPP, channel=ConsentChannel.WHATSAPP,
            evidence_reference=evidence_reference,
        )
        self._repo.save(consent)
        self._conn.commit()

    async def opt_out(self, customer_id: str, *, reason: str) -> None:
        existing = self._repo.get_latest(customer_id, _WHATSAPP)
        if existing is not None and existing.status is ConsentStatus.GRANTED:
            existing.withdraw(reason)
            self._repo.update(existing)
        elif existing is not None and existing.status is ConsentStatus.WITHDRAWN:
            return  # ya retirado — idempotente, no duplica el registro.
        else:
            declined = CustomerConsent.decline(
                customer_id, ConsentType.WHATSAPP, channel=ConsentChannel.WHATSAPP, reason=reason,
            )
            self._repo.save(declined)
        self._conn.commit()
