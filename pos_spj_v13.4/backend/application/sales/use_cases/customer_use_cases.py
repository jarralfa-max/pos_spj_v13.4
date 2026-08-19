"""Customer-in-the-POS use cases (master prompt §21-23, SALES-10/POS-10).

"Search" has no dedicated Sales use case wrapper — the master prompt itself
names `CustomerLookupQueryService` directly as what "el POS consume" (§21),
not a use-case indirection; `SalesCustomerClient.search()` (SALES-10)
exposes it as-is, permission-gated by Customer Master's own
`CustomerPermissions.SEARCH` internally. Only the two actions that need
Sales-side orchestration (creating a customer as a POS side-effect;
resolving+assigning a scanned card) get their own use case here.

Neither of these requires a `SalesPermissions` check of its own: quick-create
is gated by Customer Master's `CustomerPermissions.CREATE` (enforced inside
`CreateCustomerUseCase`, the same customer-master call
`SalesCustomerClient.quick_create` delegates to); card-scan-then-assign
reuses `AssignCustomerToSaleUseCase`'s own `SALES.crear` gate for the
assignment half — a card scan is not a new kind of action requiring its own
permission, it is a search-and-assign compound action.
"""

from __future__ import annotations

from backend.application.sales.use_cases.cart_use_cases import AssignCustomerToSaleUseCase
from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.domain.sales.exceptions import SaleCustomerNotFoundError
from backend.infrastructure.integrations.sales_customer_client import SalesCustomerClient


class QuickCreateCustomerForSaleUseCase:
    """§22: nombre + teléfono opcional, nada más — no crea membresía, tarjeta
    ni puntos (verificado leyendo `CreateCustomerUseCase` de Customer Master
    antes de conectar esto: no toca ninguna tabla de fidelidad)."""

    def __init__(self, customer_authorization=None) -> None:
        self._customer_auth = customer_authorization

    def execute(self, connection, *, actor_user_id: str, operation_id: str,
                display_name: str, phone_e164: str | None = None):
        client = SalesCustomerClient(connection, authorization=self._customer_auth)
        return client.quick_create(
            actor_user_id=actor_user_id, operation_id=operation_id,
            display_name=display_name, phone_e164=phone_e164)


class ScanLoyaltyCardForSaleUseCase:
    """§21 "escanear tarjeta" — a single real POS action, not two separate
    steps: look up the card (legacy `clientes` table, the only real card-scan
    path in this repository — confirmed by research, nothing touches the new
    `customers` table for card lookups), bridge the result into Customer
    Master's identity space (`ResolveLegacyCustomerUseCase`, CRM-21's own
    bridge — never skip this, `Sale.customer_id` must hold a `customers.id`,
    never a legacy `clientes.id`), then assign it to the sale — reusing
    `AssignCustomerToSaleUseCase` rather than duplicating its existence-check
    and event-emission logic.
    """

    def __init__(self, sales_authorization: SalesAuthorizationPolicy | None = None) -> None:
        self._sales_auth = sales_authorization

    def execute(self, connection, *, sale_id: str, card_code: str, actor_user_id: str,
                operation_id: str):
        client = SalesCustomerClient(connection)
        legacy_row = client.lookup_by_card(card_code)
        if legacy_row is None:
            from backend.application.sales.result import fail_from_domain_error

            return fail_from_domain_error(
                SaleCustomerNotFoundError(f"Ninguna tarjeta/cliente coincide con {card_code!r}"),
                operation_id=operation_id)
        customer_id = client.resolve_legacy_customer(legacy_row["id"])
        return AssignCustomerToSaleUseCase(self._sales_auth).execute(
            connection, sale_id=sale_id, customer_id=customer_id,
            actor_user_id=actor_user_id, operation_id=operation_id)
