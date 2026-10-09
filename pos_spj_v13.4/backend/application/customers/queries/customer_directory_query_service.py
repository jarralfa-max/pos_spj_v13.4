"""CustomerDirectoryQueryService (§57, §83, CRM-43) — el directorio de
clientes con lo que la tabla necesita: contacto principal (enmascarado según
permiso, §75), responsable, segmentos, crédito y última actividad.

Antes el directorio mostraba código, nombre, el tipo en crudo y el estado, y
con alcance de empresa sólo los ACTIVOS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.customers.queries.customer_display_profile import resolve_visibility
from backend.application.customers.queries.customer_profile_query_service import (
    CustomerProfileQueryService,
)
from backend.domain.customers.value_objects.field_visibility import mask
from backend.infrastructure.db.repositories.customers.customer_directory_repository import (
    CustomerDirectoryRepository,
)


@dataclass(frozen=True)
class CustomerDirectoryRow:
    customer: object
    contact_name: str = ""
    phone: str = ""
    email: str = ""
    owner_user_id: str | None = None
    segments: tuple[str, ...] = field(default_factory=tuple)
    credit_status: str = "NOT_CONFIGURED"
    last_activity_at: str | None = None


class CustomerDirectoryQueryService:
    def __init__(self, connection, scope_resolver, authorization) -> None:
        self._profiles = CustomerProfileQueryService(connection, scope_resolver)
        self._repo = CustomerDirectoryRepository(connection)
        self._auth = authorization

    def list_rows(self, context, *, limit: int = 1000) -> list[CustomerDirectoryRow]:
        customers = self._profiles.list_directory(context, limit=limit)
        visibility = resolve_visibility(self._auth, context.user_id)
        extra = self._repo.enrich(tuple(c.id for c in customers))
        rows = []
        for customer in customers:
            info = extra.get(customer.id, {})
            contact = info.get("contact") or {}
            last = max((x for x in (customer.last_purchase_at, info.get("last_activity_at"))
                        if x), default=None)
            rows.append(CustomerDirectoryRow(
                customer=customer,
                contact_name=" ".join(p for p in (contact.get("first_name"),
                                                  contact.get("last_name")) if p),
                phone=mask(contact.get("phone_e164") or "", visibility),
                email=mask(contact.get("email") or "", visibility),
                owner_user_id=info.get("owner_user_id") or customer.account_owner_user_id,
                segments=tuple(info.get("segments", ())),
                credit_status=info.get("credit_status") or "NOT_CONFIGURED",
                last_activity_at=last))
        return rows
