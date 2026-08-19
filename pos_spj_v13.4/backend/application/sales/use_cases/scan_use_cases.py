"""ScanCodeRouter — POS-12/§17's normalized scan-dispatch point.

Three real, parallel scanner mechanisms coexist in `modulos/ventas.py`
today (`LectorQR`/`LectorQRSerial`, `_ScanContextFilter`, the separate
`_scanner_timer` buffering/timing mechanism configured from
`hardware_config`), none sharing a dispatch vocabulary — confirmed by
research, not assumed. Converging their widget-level input handling is out
of scope here (this pipeline does not touch `modulos/ventas.py` beyond
narrow, justified fixes); what genuinely belongs in the application layer,
and was previously duplicated ad hoc wherever a raw scanned string needed
to become an action, is: "given a code and a context, do the one right
Sales thing" — resolve a product and add it to the cart, or resolve a
customer card and assign it. This is that single decision point, reusing
`AddSaleLineUseCase` (SALES-8) and `ScanLoyaltyCardForSaleUseCase` (SALES-10)
rather than duplicating either's logic.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.application.sales.queries.catalog_query_service import SalesCatalogQueryService
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase
from backend.application.sales.use_cases.customer_use_cases import ScanLoyaltyCardForSaleUseCase
from backend.domain.sales.enums import ScanContext
from backend.domain.sales.exceptions import ScanCodeNotResolvedError


class ScanCodeRouter:
    def __init__(self, sales_authorization: SalesAuthorizationPolicy | None = None) -> None:
        self._sales_auth = sales_authorization

    def route(
        self, connection, *, sale_id: str, code: str, context: ScanContext,
        branch_id: str, actor_user_id: str, operation_id: str,
    ) -> SaleResult:
        code = (code or "").strip()
        if not code:
            return fail_from_domain_error(
                ScanCodeNotResolvedError("Código escaneado vacío"), operation_id=operation_id)

        if context in (ScanContext.PRODUCT, ScanContext.AUTO):
            product = SalesCatalogQueryService(connection).find_by_code(branch_id=branch_id, code=code)
            if product is not None:
                return AddSaleLineUseCase(self._sales_auth).execute(
                    connection, sale_id=sale_id, product_id=product.product_id,
                    quantity=Decimal("1"), unit_price=product.effective_price,
                    actor_user_id=actor_user_id, operation_id=operation_id,
                    product_snapshot={"name": product.name, "sku": product.sku})
            if context is ScanContext.PRODUCT:
                return fail_from_domain_error(
                    ScanCodeNotResolvedError(f"Ningún producto coincide con {code!r}"),
                    operation_id=operation_id)

        return ScanLoyaltyCardForSaleUseCase(self._sales_auth).execute(
            connection, sale_id=sale_id, card_code=code, actor_user_id=actor_user_id,
            operation_id=operation_id)
