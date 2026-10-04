"""Cupones en la venta (2026-10-03): el cupón es un DESCUENTO del ticket.

Fidelidad decide si aplica —vigencia, dueño, combinación con puntos u otros
cupones según la política configurada (§24)— y lo aparta para esta venta;
Ventas sólo registra su respuesta (`Sale.apply_coupon`). Se canjea al
completar la venta (Fidelidad, por el bus) y se libera si se quita del ticket
o la venta se cancela.

Mismo permiso que canjear puntos (`POS.venta.completar`): aplicar un beneficio
es parte de cerrar la venta, no una capacidad aparte.
"""

from __future__ import annotations

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import SalesDomainError, SaleNotFoundError
from backend.domain.sales.value_objects.sale_coupon import SaleCoupon
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_instruments_client import SalesInstrumentsClient

COUPON_APPLIED = SaleEvents.COUPON_APPLIED
COUPON_REMOVED = SaleEvents.COUPON_REMOVED


class ApplyCouponToSaleUseCase(_SalesBaseUseCase):
    def execute(self, connection, *, sale_id: str, code: str, actor_user_id: str,
                operation_id: str) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_COMPLETE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            if any(c.code.upper() == str(code or "").strip().upper() for c in sale.coupons):
                return SaleResult.fail("Ese cupón ya está aplicado", "COUPON_REJECTED",
                                       operation_id=operation_id)
            cliente = SalesInstrumentsClient(connection, actor_branch_id=sale.branch_id)
            respuesta = cliente.apply_coupon(sale=sale, code=code, actor_user_id=actor_user_id)
            if not respuesta["approved"]:
                return SaleResult.fail(respuesta["reason"], "COUPON_REJECTED",
                                       operation_id=operation_id)
            try:
                cupon = sale.apply_coupon(SaleCoupon.create(
                    sale_id=sale.id, coupon_instance_id=respuesta["coupon_instance_id"],
                    code=respuesta["code"], benefit_type=respuesta["benefit_type"],
                    benefit_value=respuesta["benefit_value"]))
            except (SalesDomainError, ValueError) as exc:
                cliente.release_coupon(coupon_instance_id=respuesta["coupon_instance_id"],
                                       actor_user_id=actor_user_id)
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, COUPON_APPLIED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id,
                       coupon_instance_id=cupon.coupon_instance_id, code=cupon.code,
                       amount=str(cupon.amount))
        return SaleResult.ok(f"Cupón {cupon.code}: -${cupon.amount:,.2f}", entity_id=sale.id,
                             operation_id=operation_id, sale=SaleDTO.from_entity(sale))


class RemoveCouponFromSaleUseCase(_SalesBaseUseCase):
    def execute(self, connection, *, sale_id: str, coupon_instance_id: str, actor_user_id: str,
                operation_id: str) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_COMPLETE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            try:
                cupon = sale.remove_coupon(coupon_instance_id)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, COUPON_REMOVED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id,
                       coupon_instance_id=coupon_instance_id)
        SalesInstrumentsClient(connection, actor_branch_id=sale.branch_id).release_coupon(
            coupon_instance_id=cupon.coupon_instance_id, actor_user_id=actor_user_id)
        return SaleResult.ok("Cupón retirado", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class SellPrepaidVoucherUseCase(_SalesBaseUseCase):
    """Vende un vale PREPAGADO como una línea más del ticket (decisión del
    usuario, 2026-10-03): el dinero entra con el cobro normal (caja/turno) y el
    vale se activa con su saldo al cobrar. La línea no es mercancía: no sale de
    inventario, no tiene costo, no acumula puntos y se asienta como pasivo."""

    def execute(self, connection, *, sale_id: str, definition_id: str, amount, actor_user_id: str,
                operation_id: str) -> SaleResult:
        from decimal import Decimal, InvalidOperation

        from backend.domain.sales.entities import INSTRUMENT_LINE_KIND
        from backend.domain.sales.value_objects.quantity import Quantity

        try:
            self._auth.require(actor_user_id, SalesPermissions.LINE_ADD)
            monto = Decimal(str(amount))
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        except InvalidOperation:
            return SaleResult.fail("Monto inválido", "VALIDATION", operation_id=operation_id)
        if monto <= 0:
            return SaleResult.fail("El vale debe tener un monto mayor a cero", "VALIDATION",
                                   operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            vale = SalesInstrumentsClient(connection, actor_branch_id=sale.branch_id) \
                .prepare_prepaid(sale=sale, definition_id=definition_id)
            if not vale["approved"]:
                return SaleResult.fail(vale["reason"], "VALIDATION", operation_id=operation_id)
            try:
                sale.add_line(
                    product_id=vale["voucher_instance_id"], quantity=Quantity(Decimal("1"), "PZA"),
                    unit_price=monto, product_snapshot={
                        "kind": INSTRUMENT_LINE_KIND, "name": f"Vale prepagado {vale['code']}",
                        "sku": vale["code"], "unit": "PZA",
                        "voucher_instance_id": vale["voucher_instance_id"],
                        "code": vale["code"]})
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.LINE_ADDED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id,
                       product_id=vale["voucher_instance_id"], quantity="1",
                       unit_price=str(monto))
        return SaleResult.ok(f"Vale prepagado {vale['code']} agregado", entity_id=sale.id,
                             operation_id=operation_id, sale=SaleDTO.from_entity(sale))


__all__ = ["ApplyCouponToSaleUseCase", "RemoveCouponFromSaleUseCase", "SellPrepaidVoucherUseCase"]
