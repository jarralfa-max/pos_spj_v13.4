"""SalesCreditClient — Sales' integration point onto the real credit
authorization/CxC path (POS-13/§30-36, "Credit").

Research for this phase confirmed a genuine, real inconsistency risk
already flagged by SALES-0: `modulos/ventas.py::procesar_pago` runs THREE
(closer to four, counting a duplicate inner check) independently-written
credit checks — a non-blocking CRM advisory query, the real enforcement
path (`application/services/customer_credit_service.py::
CustomerCreditService.validate_credit`), and an inline fallback re-deriving
credit limit directly from `clientes` whenever `customer_credit_service`
isn't wired on the container (which, per the same research, then makes the
DEEPER `SalesService._validate_payment` check unconditionally block the
sale anyway, since it shares the same `None` service reference — so that
third path's approval is effectively moot whenever it would run).

This client does not touch or fix any of those three legacy paths (out of
scope — `modulos/ventas.py` stays untouched per this pipeline's own
discipline). What it gives the NEW `Sale` aggregate is ONE clean path onto
the real enforcement service (`CustomerCreditService.validate_credit`,
confirmed research path #2, the one that actually blocks), so any future
caller building on `backend/application/sales/` never has to choose between
three divergent implementations the way the legacy UI does today.

`CustomerCreditService` only understands legacy `clientes.id`; `Sale.
customer_id` holds a Customer Master `customers.id` — bridged via
`EnsureLegacyCustomerBridgeUseCase`, the same new->legacy bridge direction
`SalesLoyaltyClient` already uses (SALES-11), for the same reason.
"""

from __future__ import annotations

from decimal import Decimal

from application.services.customer_credit_service import CustomerCreditService
from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
    EnsureLegacyCustomerBridgeUseCase,
)


class SalesCreditClient:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._service = CustomerCreditService(connection)

    def validate(self, *, customer_id: str, amount: Decimal) -> tuple[bool, str]:
        """(True, "") if `customer_id` (a Customer Master id) is authorized
        to place `amount` on credit; (False, reason) otherwise. Never
        raises for a business rejection — same contract as the wrapped
        legacy service, translated at this boundary, not hidden."""
        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(
            self._connection, customer_id=customer_id)
        return self._service.validate_credit(legacy_id, float(amount))

    def register(self, *, customer_id: str, sale_id: str, folio: str, amount: Decimal,
                 branch_id: str) -> None:
        """Records the CxC debt for a completed credit sale — idempotent by
        `sale_id` (the wrapped service's own `INSERT OR IGNORE` on a unique
        index), so calling this more than once for the same sale is safe."""
        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(
            self._connection, customer_id=customer_id)
        self._service.register_credit_sale(legacy_id, sale_id, folio, float(amount), branch_id)
