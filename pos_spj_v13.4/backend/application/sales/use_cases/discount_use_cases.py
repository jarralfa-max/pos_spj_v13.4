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
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import SalesDomainError, SaleNotFoundError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork


class ApplySaleDiscountUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, discount_amount: Decimal, actor_user_id: str,
        operation_id: str, authorizer_user_id: str | None = None, reason: str | None = None,
    ) -> SaleResult:
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
                    self._auth.authorize_exception(
                        authorizer_user_id=authorizer_user_id, requested_by=actor_user_id,
                        permission_code=SalesPermissions.DISCOUNT_OVERRIDE,
                        operation_id=operation_id, reason=reason or "",
                        amount=discount_amount, sale_id=sale_id)
                except SalesDomainError as exc:
                    return fail_from_domain_error(exc, operation_id=operation_id)
                authorized = True

            try:
                sale.apply_sale_discount(discount_amount, authorized=authorized)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.DISCOUNT_APPLIED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, amount=str(discount_amount),
                       authorized_by=authorizer_user_id)
        return SaleResult.ok("Descuento aplicado", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class ApplyLineDiscountUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, line_id: str, discount_amount: Decimal,
        actor_user_id: str, operation_id: str, authorizer_user_id: str | None = None,
        reason: str | None = None,
    ) -> SaleResult:
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
                    self._auth.authorize_exception(
                        authorizer_user_id=authorizer_user_id, requested_by=actor_user_id,
                        permission_code=SalesPermissions.DISCOUNT_OVERRIDE,
                        operation_id=operation_id, reason=reason or "",
                        amount=discount_amount, sale_id=sale_id)
                except SalesDomainError as exc:
                    return fail_from_domain_error(exc, operation_id=operation_id)
                authorized = True

            try:
                sale.apply_line_discount(line_id, discount_amount, authorized=authorized)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.DISCOUNT_APPLIED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, amount=str(discount_amount),
                       authorized_by=authorizer_user_id, line_id=line_id)
        return SaleResult.ok("Descuento de línea aplicado", entity_id=sale.id,
                             operation_id=operation_id, sale=SaleDTO.from_entity(sale))
