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
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
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
        return [CustomerLookupResult(
            customer_id=row["id"], code=row["customer_number"],
            display_name=row["display_name"], legal_name=row["legal_name"] or "",
            status=row["status"], phone_e164=row["phone_e164"], email=row["email"])
            for row in rows]
