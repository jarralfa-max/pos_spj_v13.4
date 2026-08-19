"""SaleBenefitEvaluationService — composes `SaleBenefitEvaluationDTO`
(master prompt §24: carrito cambia → Sales solicita evaluación → Pricing y
Promotions evalúan → Loyalty evalúa beneficios → Sales recibe breakdown →
UI presenta).

Mirrors `backend/application/customers/queries/customer_360_query_service.py`'s
own composition shape (confirmed via research to be this repo's established
precedent for "compose several other bounded contexts' outputs into one
DTO, one hard gate, everything else independently degraded on failure" —
its own docstring: "pure composition... never re-implements a query another
service already owns"). One hard gate here (the sale itself must exist);
loyalty evaluation degrades to zero + a warning on any failure, exactly
like Customer360's own `_safe()` helper — never raises past that point.

Promotions/coupons/vouchers are hardcoded zero with an explicit warning,
not silently omitted — confirmed by research that no owning bounded context
exists anywhere in this repository for any of the three (no
`backend/domain/promotions/`, no coupon/voucher catalog table, only
Finance's downstream accounting-recognition tail for already-decided
amounts). Fabricating an evaluator for them here would be exactly the kind
of decorative infrastructure this pipeline has repeatedly refused to build
without a real integration point (SALES-4/5's outbox dispatcher, SALES-9's
`ExpireOrphanedInventoryReservationsUseCase` reasoning).
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.sales.dto import SaleBenefitEvaluationDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.domain.sales.exceptions import SaleNotFoundError
from backend.domain.sales.policies.discount_policy import SaleDiscountPolicy
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.integrations.sales_loyalty_client import SalesLoyaltyClient

_NO_PROMOTIONS_ENGINE = (
    "Promociones: no existe un bounded context de Promotions en este repositorio "
    "todavía — descuento de promoción siempre 0.")
_NO_COUPONS_ENGINE = (
    "Cupones: no existe catálogo de cupones en este repositorio todavía — "
    "descuento de cupón siempre 0.")
_NO_VOUCHERS_ENGINE = (
    "Vales: no existe catálogo de vales en este repositorio todavía — "
    "monto de vale siempre 0.")


class SaleBenefitEvaluationService:
    def __init__(self, connection, authorization: SalesAuthorizationPolicy | None = None) -> None:
        self._connection = connection
        self._auth = authorization or SalesAuthorizationPolicy()

    def evaluate(self, sale_id: str, *, requester_user_id: str) -> SaleBenefitEvaluationDTO:
        self._auth.require(requester_user_id, SalesPermissions.VIEW)
        sale = SaleRepository(self._connection).get(sale_id)
        if sale is None:
            raise SaleNotFoundError(f"Venta {sale_id} no existe")

        commercial_discount = sale.totals.discount_total
        requires_manual_authorization = SaleDiscountPolicy.requires_authorization(
            discount_amount=commercial_discount, base_amount=sale.totals.gross_subtotal)

        warnings: list[str] = [_NO_PROMOTIONS_ENGINE, _NO_COUPONS_ENGINE, _NO_VOUCHERS_ENGINE]
        loyalty_points_available = 0
        loyalty_max_redemption_value = Decimal("0")

        if sale.customer_id is None:
            warnings.append("Sin cliente asignado — beneficios de fidelidad no evaluados")
        else:
            try:
                preview = SalesLoyaltyClient(self._connection).preview_redemption(
                    customer_id=sale.customer_id, subtotal=sale.totals.total)
            except Exception:  # noqa: BLE001 - degrade like Customer360's _safe(), never raise
                warnings.append("No se pudo evaluar fidelidad para este cliente")
            else:
                if preview.get("enabled"):
                    loyalty_points_available = int(preview.get("puntos_maximos_canjeables", 0) or 0)
                    loyalty_max_redemption_value = Decimal(str(preview.get("descuento_maximo", 0) or 0))
                else:
                    warnings.append(
                        preview.get("mensaje") or "Programa de fidelidad no disponible para este cliente")

        return SaleBenefitEvaluationDTO(
            sale_id=sale.id,
            commercial_discount=commercial_discount,
            requires_manual_authorization=requires_manual_authorization,
            loyalty_points_available=loyalty_points_available,
            loyalty_max_redemption_value=loyalty_max_redemption_value,
            warnings=tuple(warnings),
        )
