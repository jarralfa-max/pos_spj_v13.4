"""Discount use cases — the ones that exercise SALES-2's hot-authorization
machinery for real (master prompt §26: descuento alto requiere autorización).
If the discount is small the domain policy lets it through directly; if
it's large, the caller must supply `authorizer_user_id`+`reason` so
`SalesAuthorizationPolicy.authorize_exception()` can validate a second,
distinct user actually holds `SalesPermissions.DISCOUNT_OVERRIDE` before the
discount is applied.

`ApplyLineDiscountUseCase` (SALES-8/POS-8) was the one action master prompt
§12's own canonical list names (`ApplyLineDiscountUseCase` alongside
`ApplySaleDiscountUseCase`/`AddSaleLineUseCase`/etc.) that SALES-6 hadn't
built yet, even though the domain method it wraps
(`Sale.apply_line_discount`) has existed since SALES-3.

PRECIO MÍNIMO (Fase 5, decisión del usuario 2026-09-18)
-------------------------------------------------------
Un descuento que deja el precio efectivo de una línea bajo su mínimo pide la
misma autorización en caliente que un descuento grande, exige motivo y queda en
el evento `SALE_DISCOUNT_APPLIED` (outbox persistido) con las líneas afectadas.
Antes el mínimo sólo existía en Precios: Ventas no lo consultaba nunca.

EL AUTORIZADOR
--------------
`authorizer_authorization` es la política con la que se valida al AUTORIZADOR.
En producción lleva `AuthorizerPermissionChecker`: el verificador de sesión sólo
responde por el cajero, así que con él —el único que se inyectaba— ningún
descuento que necesitara autorización podía aprobarse jamás desde el mostrador.
Sin ella se usa la política normal (el comportamiento de las pruebas).
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.policies.minimum_price_policy import MinimumPricePolicy
from backend.domain.sales.exceptions import SalesDomainError, SaleNotFoundError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork


class _DiscountUseCase(_SalesBaseUseCase):
    """Autorización, precio mínimo y emisión comunes a ambos descuentos."""

    def __init__(self, authorization=None, *, authorizer_authorization=None,
                 minimum_prices=None, **kwargs) -> None:
        super().__init__(authorization, **kwargs)
        self._authorizer_auth = authorizer_authorization or self._auth
        #: Puerto de Precios: `minimum_price(product_id, *, branch_id,
        #: customer_id, quantity)` -> Decimal | None (`SalesPricingClient`).
        self._minimum_prices = minimum_prices

    def _authorize(self, *, authorizer_user_id, actor_user_id, operation_id, reason,
                   discount_amount, sale_id) -> None:
        self._authorizer_auth.authorize_exception(
            authorizer_user_id=authorizer_user_id, requested_by=actor_user_id,
            permission_code=SalesPermissions.DISCOUNT_OVERRIDE,
            operation_id=operation_id, reason=reason or "",
            amount=discount_amount, sale_id=sale_id)

    def _below_minimum(self, sale) -> list:
        if self._minimum_prices is None:
            return []
        minimos = {
            linea.id: self._minimum_prices.minimum_price(
                linea.product_id, branch_id=sale.branch_id, customer_id=sale.customer_id,
                quantity=linea.quantity.value)
            for linea in sale.lines
        }
        return MinimumPricePolicy.lines_below_minimum(
            sale.lines, minimums=minimos, sale_level_discount=sale.sale_level_discount)

    @staticmethod
    def _minimum_failure(debajo, *, authorized: bool, reason, operation_id):
        """`None` si el descuento puede seguir; si no, el fallo a devolver."""
        if not debajo:
            return None
        detalle = ", ".join(
            "$" + str(d.effective_unit_price) + " < mínimo $" + str(d.minimum_price)
            for d in debajo)
        if not authorized:
            return SaleResult.fail(
                f"El descuento deja el precio bajo el mínimo ({detalle}): "
                "requiere autorización de otro usuario", "BELOW_MINIMUM",
                operation_id=operation_id)
        if not (reason or "").strip():
            return SaleResult.fail(
                "Vender bajo el precio mínimo requiere un motivo", "BELOW_MINIMUM",
                operation_id=operation_id)
        return None

    def _run(self, connection, *, sale_id, discount_amount, actor_user_id, operation_id,
             authorizer_user_id, reason, apply, line_id=None, message) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.DISCOUNT_APPLY)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)

            authorized = False
            if authorizer_user_id is not None:
                try:
                    self._authorize(
                        authorizer_user_id=authorizer_user_id, actor_user_id=actor_user_id,
                        operation_id=operation_id, reason=reason,
                        discount_amount=discount_amount, sale_id=sale_id)
                except SalesDomainError as exc:
                    return fail_from_domain_error(exc, operation_id=operation_id)
                authorized = True

            try:
                apply(sale, authorized)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            # Se evalúa DESPUÉS de aplicar: el precio efectivo depende del
            # descuento nuevo y de los que ya tenía la venta. Si falla, la venta
            # no se guarda (el cambio sólo vivía en memoria).
            debajo = self._below_minimum(sale)
            fallo = self._minimum_failure(debajo, authorized=authorized, reason=reason,
                                          operation_id=operation_id)
            if fallo is not None:
                return fallo
            uow.sales.save(sale)
            extra = {"line_id": line_id} if line_id is not None else {}
            if debajo:
                extra["below_minimum"] = [d.as_payload() for d in debajo]
            self._emit(uow, SaleEvents.DISCOUNT_APPLIED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, amount=str(discount_amount),
                       authorized_by=authorizer_user_id, reason=reason or None, **extra)
        return SaleResult.ok(message, entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class ApplySaleDiscountUseCase(_DiscountUseCase):
    def execute(
        self, connection, *, sale_id: str, discount_amount: Decimal, actor_user_id: str,
        operation_id: str, authorizer_user_id: str | None = None, reason: str | None = None,
    ) -> SaleResult:
        return self._run(
            connection, sale_id=sale_id, discount_amount=discount_amount,
            actor_user_id=actor_user_id, operation_id=operation_id,
            authorizer_user_id=authorizer_user_id, reason=reason,
            apply=lambda sale, authorized: sale.apply_sale_discount(
                discount_amount, authorized=authorized),
            message="Descuento aplicado")


class ApplyLineDiscountUseCase(_DiscountUseCase):
    def execute(
        self, connection, *, sale_id: str, line_id: str, discount_amount: Decimal,
        actor_user_id: str, operation_id: str, authorizer_user_id: str | None = None,
        reason: str | None = None,
    ) -> SaleResult:
        return self._run(
            connection, sale_id=sale_id, discount_amount=discount_amount,
            actor_user_id=actor_user_id, operation_id=operation_id,
            authorizer_user_id=authorizer_user_id, reason=reason,
            apply=lambda sale, authorized: sale.apply_line_discount(
                line_id, discount_amount, authorized=authorized),
            line_id=line_id, message="Descuento de línea aplicado")
