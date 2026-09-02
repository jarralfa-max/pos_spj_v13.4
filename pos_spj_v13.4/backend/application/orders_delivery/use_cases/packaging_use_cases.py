"""Packaging use cases (master prompt §29). Gated by `PREPARATION_COMPLETE`
— no dedicated "empaque.*" permission exists in the ORD-1 catalog (the
master prompt's own §63 list doesn't define one either); packaging is the
last preparation step before dispatch-readiness, same tier as completing
preparation.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.enums import PackageType
from backend.domain.orders_delivery.exceptions import (
    InvalidPackageError,
    OrderLineNotFoundError,
    OrderNotFoundError,
    OrdersDeliveryDomainError,
)
from backend.domain.orders_delivery.package import OrderPackage
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)


class CreatePackageUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, order_id: str, package_number: str,
        package_type: PackageType | str, line_ids: list[str], actor_user_id: str,
        operation_id: str, tare: Decimal = Decimal("0"), gross_weight: Decimal = Decimal("0"),
        temperature: Decimal | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.PREPARATION_COMPLETE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        package_type = (package_type if isinstance(package_type, PackageType)
                         else PackageType(package_type))
        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            order_line_ids = {line.id for line in order.lines}
            for line_id in line_ids:
                if line_id not in order_line_ids:
                    return fail_from_domain_error(
                        OrderLineNotFoundError(f"Línea {line_id} no pertenece al pedido"),
                        operation_id=operation_id)
            try:
                package = OrderPackage.create(
                    order_id=order_id, package_number=package_number,
                    package_type=package_type, line_ids=tuple(line_ids), tare=tare,
                    gross_weight=gross_weight, temperature=temperature)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            for line in order.lines:
                if line.id in line_ids:
                    line.set_package(package.id)
            uow.packages.save(package)
            uow.orders.save(order)
        return OrderResult.ok(
            "Paquete creado", entity_id=package.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order), package_id=package.id,
            net_weight=package.net_weight)


class SealPackageUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, package_id: str, seal_number: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.PREPARATION_COMPLETE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            package = uow.packages.get(package_id)
            if package is None:
                return fail_from_domain_error(
                    InvalidPackageError(f"Paquete {package_id} no existe"),
                    operation_id=operation_id)
            try:
                package.seal(seal_number=seal_number)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.packages.save(package)
        return OrderResult.ok(
            "Paquete sellado", entity_id=package.id, operation_id=operation_id,
            seal_number=package.seal_number)
