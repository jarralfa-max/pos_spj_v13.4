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
    """§21 "escanear tarjeta" — una sola acción del POS: identificar y asignar.

    LOY-29: primero se pregunta a Fidelidad qué tarjeta es
    (`ResolveLoyaltyCardQuery`, vía `SalesLoyaltyClient.resolve_card`). Antes el
    código se buscaba SÓLO en la tabla legacy `clientes`, así que ninguna
    tarjeta emitida por el módulo canónico identificaba al cliente. Una tarjeta
    bloqueada, repuesta o con QR revocado se rechaza con el motivo de Fidelidad.

    Si lo escaneado no es una tarjeta, se sigue buscando como antes en Clientes
    (credencial, teléfono, código impreso): esa búsqueda es de Clientes, no un
    respaldo de tarjetas. La asignación reutiliza `AssignCustomerToSaleUseCase`.
    """

    def __init__(self, sales_authorization: SalesAuthorizationPolicy | None = None) -> None:
        self._sales_auth = sales_authorization

    def execute(self, connection, *, sale_id: str, card_code: str, actor_user_id: str,
                operation_id: str):
        from backend.application.sales.result import fail_from_domain_error
        from backend.infrastructure.integrations.sales_loyalty_client import SalesLoyaltyClient

        tarjeta = SalesLoyaltyClient(connection).resolve_card(card_code)
        if tarjeta.found:
            if not tarjeta.eligible or not tarjeta.customer_id:
                return fail_from_domain_error(
                    SaleCustomerNotFoundError(" ".join(tarjeta.warnings)
                                              or "La tarjeta no puede usarse."),
                    operation_id=operation_id)
            customer_id = tarjeta.customer_id
        else:
            client = SalesCustomerClient(connection)
            legacy_row = client.lookup_by_card(card_code)
            if legacy_row is None:
                return fail_from_domain_error(
                    SaleCustomerNotFoundError(
                        f"Ninguna tarjeta/cliente coincide con {card_code!r}"),
                    operation_id=operation_id)
            customer_id = client.resolve_legacy_customer(legacy_row["id"])
        return AssignCustomerToSaleUseCase(self._sales_auth).execute(
            connection, sale_id=sale_id, customer_id=customer_id,
            actor_user_id=actor_user_id, operation_id=operation_id)
