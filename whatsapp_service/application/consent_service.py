# application/consent_service.py — WA-14 (§44 del prompt maestro)
"""
ConsentService — capa de aplicación sobre `ConsentApiClient` (WA-14). Hace
UNA cosa que el puerto/adaptador deliberadamente no hace: traducir el
`customer_external_id` que el resto del canal ya conoce (el `clientes.id`
legacy que devuelven `CustomersApiClient.find_by_phone`/`create_minimal`,
WA-9) hacia el `customers.id` (Customer Master, CRM-3) que
`customer_consents`/`_is_whatsapp_opted_out` (CRM-31) realmente usan — son
DOS tablas con UUIDs independientes (`legacy_customer_bridge_use_cases.py`,
CRM-21). Sin este puente, un `grant()`/`opt_out()` escrito con el id
equivocado nunca sería leído por el gate real de envío.

`ResolveLegacyCustomerUseCase` nunca lanza (crea el puente si falta) — ver
su propio docstring: "callers... must never fail a sale or a chat reply
over a bridging gap". Mismo criterio se aplica aquí.
"""
from __future__ import annotations

from typing import Optional


class ConsentService:
    def __init__(self, root) -> None:
        self._root = root

    def _resolve_customer_id(self, customer_external_id: str) -> str:
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            ResolveLegacyCustomerUseCase,
        )

        return ResolveLegacyCustomerUseCase().execute(
            self._root.connection, legacy_customer_id=customer_external_id,
        )

    async def get_status(self, *, customer_external_id: str) -> Optional[str]:
        customer_id = self._resolve_customer_id(customer_external_id)
        return await self._root.consent.get_status(customer_id)

    async def is_opted_out(self, *, customer_external_id: str) -> bool:
        status = await self.get_status(customer_external_id=customer_external_id)
        return status == "WITHDRAWN"

    async def record_opt_in(self, *, customer_external_id: str, evidence_reference: str) -> None:
        customer_id = self._resolve_customer_id(customer_external_id)
        await self._root.consent.grant(customer_id, evidence_reference=evidence_reference)

    async def record_opt_out(self, *, customer_external_id: str, reason: str) -> None:
        customer_id = self._resolve_customer_id(customer_external_id)
        await self._root.consent.opt_out(customer_id, reason=reason)
