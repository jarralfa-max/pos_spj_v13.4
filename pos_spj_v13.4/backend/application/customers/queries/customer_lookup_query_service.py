"""CustomerLookupQueryService (§49, §57) — fast search-as-you-type lookup.
Reads only; never mutates. §49: "Ventas consume CustomerLookupQueryService"
— this is the one query service in the Customer Master package
deliberately NOT scope-restricted via CustomerDataScopeResolver: a cashier
at a register needs to find any active customer by name/phone/email, not
just the ones in their own OWN/TEAM/BRANCH grant. Gated by the flat
``SEARCH`` permission instead (already distinct from ``GLOBAL_SEARCH``,
which CRM-2 reserved for a wider, more privileged search surface this
service doesn't need).

Returns a lightweight DTO, never the full ``Customer`` aggregate —
``CustomerRepository.search_lookup()`` was built specifically to stay
cheap per keystroke.

Auditoría CRM F04 (2026-10-09): «puede seleccionar al cliente» no es «puede
ver su teléfono y correo». Con sólo ``SEARCH`` el teléfono y el correo llegaban
en claro; ahora pasan por la MISMA política de visibilidad que el expediente
(``resolve_visibility``: completo con datos sensibles, parcial con permiso de
contactos, enmascarado sin él). La búsqueda por teléfono sigue funcionando: se
compara en el servidor, sólo se enmascara lo que se devuelve.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.queries.customer_display_profile import resolve_visibility
from backend.domain.customers.value_objects.field_visibility import FieldVisibility, mask
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


@dataclass(frozen=True)
class CustomerLookupResult:
    customer_id: str
    code: str
    display_name: str
    legal_name: str
    status: str
    phone_e164: str | None
    email: str | None


class CustomerLookupQueryService:
    def __init__(self, connection,
                authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerUnitOfWork(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def lookup(self, query: str, *, actor_user_id: str,
              limit: int = 20) -> list[CustomerLookupResult]:
        self._auth.require(actor_user_id, CustomerPermissions.SEARCH)
        if not query or not query.strip():
            return []
        rows = self._uow.customers.search_lookup(query.strip(), limit=limit)
        visibility = resolve_visibility(self._auth, actor_user_id)
        return [self._result(row, visibility) for row in rows]

    @staticmethod
    def _result(row, visibility: FieldVisibility) -> CustomerLookupResult:
        def shown(value):
            return value if value in (None, "") else mask(str(value), visibility)
        return CustomerLookupResult(
            customer_id=row["id"], code=row["customer_number"],
            display_name=row["display_name"], legal_name=row["legal_name"] or "",
            status=row["status"], phone_e164=shown(row["phone_e164"]),
            email=shown(row["email"]))

    def get(self, customer_id: str, *, actor_user_id: str) -> CustomerLookupResult | None:
        """El cliente asignado a una venta, por id (§21: "mostrar" el cliente
        que el POS identificó). Mismo permiso y misma forma que `lookup`."""
        self._auth.require(actor_user_id, CustomerPermissions.SEARCH)
        if not customer_id:
            return None
        row = self._uow.customers.lookup_row(customer_id)
        if row is None:
            return None
        return self._result(row, resolve_visibility(self._auth, actor_user_id))

