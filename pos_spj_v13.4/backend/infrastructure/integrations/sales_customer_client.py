"""SalesCustomerClient — Sales' integration point onto Customer Master
(master prompt §6/§21: "Clientes sigue siendo dueño de identidad"; §8.4
names `pricing_client.py`/`inventory_client.py` as this exact adapter shape
for other contexts — this is the customer equivalent). Mirrors
`sales_inventory_client.py`'s shape: constructor-injected connection, thin
per-action methods delegating to the REAL owning bounded context's own
use cases/query services — never SQL against `customers`/`clientes` beyond
a bare existence check, never a duplicated `CreateCustomerUseCase`.

Two identity spaces meet at this boundary, same problem CRM-21 already
solved once: `Sale.customer_id` is meant to hold a Customer Master
`customers.id`, but the only real loyalty-card-scan lookup in this
repository (`repositories.cliente_repository.ClienteRepository.get_by_scanner`,
confirmed via research to be the actual live path — no card-scan code
anywhere touches the new `customers` table) can only ever resolve a legacy
`clientes.id`. `lookup_by_card()` returns the legacy row as-is;
`resolve_legacy_customer()` (wrapping the existing
`ResolveLegacyCustomerUseCase` from CRM-21) is the mandatory bridging step
before that id is usable as `Sale.customer_id` — never skip it for a
card-scan result.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.queries.customer_lookup_query_service import (
    CustomerLookupQueryService,
    CustomerLookupResult,
)
from backend.application.customers.result import CustomerResult
from backend.application.customers.use_cases.contact_use_cases import AddCustomerContactUseCase
from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
    ResolveLegacyCustomerUseCase,
)
from backend.application.customers.use_cases.lifecycle_use_cases import (
    CreateCustomerUseCase as CustomerMasterCreateCustomerUseCase,
)
from backend.shared.ids import new_uuid


class SalesCustomerClient:
    def __init__(self, connection, *, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._connection = connection
        self._auth = authorization

    def search(self, query: str, *, actor_user_id: str, limit: int = 20) -> list[CustomerLookupResult]:
        """Deliberately no Sales-side permission check here — Customer
        Master's own `CustomerLookupQueryService` already requires
        `CustomerPermissions.SEARCH` internally and is the single source of
        truth for who can search customer records, cross-context."""
        service = CustomerLookupQueryService(self._connection, self._auth)
        return service.lookup(query, actor_user_id=actor_user_id, limit=limit)

    def quick_create(
        self, *, actor_user_id: str, operation_id: str, display_name: str,
        phone_e164: str | None = None,
    ) -> CustomerResult:
        """§22: only name + optional phone. Never creates a loyalty
        card/membership/points balance — confirmed by reading Customer
        Master's own `CreateCustomerUseCase` before wiring this: it only
        touches `customers`, audit, and its own outbox event, nothing
        loyalty-adjacent."""
        use_case = CustomerMasterCreateCustomerUseCase(self._auth)
        result = use_case.execute(
            self._connection, actor_user_id=actor_user_id, display_name=display_name,
            operation_id=operation_id, phone_e164=phone_e164)
        if result.success and phone_e164:
            AddCustomerContactUseCase(self._auth).execute(
                self._connection, actor_user_id=actor_user_id, customer_id=result.entity_id,
                first_name=display_name, phone_e164=phone_e164, is_primary=True,
                operation_id=new_uuid())
        return result

    def exists(self, customer_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM customers WHERE id=?", (customer_id,)).fetchone()
        return row is not None

    def resolve_legacy_customer(self, legacy_customer_id: str) -> str:
        return ResolveLegacyCustomerUseCase().execute(
            self._connection, legacy_customer_id=legacy_customer_id, source="sales_pos_scan")

    def lookup_by_card(self, card_code: str) -> dict | None:
        """Legacy-table lookup (confirmed the only real card-scan path in
        this repository) — returns a raw `clientes` row dict, a LEGACY id.
        Callers must pass it through `resolve_legacy_customer()` before
        using it as `Sale.customer_id`."""
        from repositories.cliente_repository import ClienteRepository

        return ClienteRepository(self._connection).get_by_scanner(card_code)
