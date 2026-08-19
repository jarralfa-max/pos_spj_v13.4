"""Cart-building use cases: start a sale, add/update/remove lines, assign a
customer. Mirrors backend/application/customers/use_cases/lifecycle_use_cases.py's
`CreateCustomerUseCase`/`UpdateCustomerUseCase` shape: permission check
before opening the UnitOfWork, domain exceptions translated to
`SaleResult.fail(...)` via one shared mapping table (`fail_from_domain_error`)
instead of a bespoke try/except per exception type.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.entities import Sale
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import (
    SaleCustomerNotFoundError,
    SalesDomainError,
    SaleNotFoundError,
)
from backend.domain.sales.value_objects.quantity import Quantity
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork


class StartSaleUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, branch_id: str, cashier_user_id: str, operation_id: str,
        actor_user_id: str, workstation_id: str | None = None,
        cash_session_id: str | None = None, channel: str = "POS",
        currency_code: str = "MXN",
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_CREATE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            existing = uow.sales.get_by_operation_id(operation_id)
            if existing is not None:
                return SaleResult.ok("Venta ya iniciada", entity_id=existing.id,
                                     operation_id=operation_id)
            try:
                sale = Sale.start(
                    branch_id=branch_id, cashier_user_id=cashier_user_id,
                    operation_id=operation_id, workstation_id=workstation_id,
                    cash_session_id=cash_session_id, channel=channel,
                    currency_code=currency_code)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.STARTED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=branch_id, actor_user_id=actor_user_id)
        return SaleResult.ok("Venta iniciada", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class AddSaleLineUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, product_id: str, quantity: Decimal,
        unit_price: Decimal, actor_user_id: str, operation_id: str,
        quantity_unit: str = "PZA", product_snapshot: Mapping[str, Any] | None = None,
        pricing_snapshot_id: str | None = None, weight_source: str | None = None,
        lot_reference: str | None = None, max_sellable: Decimal | None = None,
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.LINE_ADD)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            try:
                line = sale.add_line(
                    product_id=product_id, quantity=Quantity(quantity, quantity_unit),
                    unit_price=unit_price, product_snapshot=product_snapshot,
                    pricing_snapshot_id=pricing_snapshot_id, weight_source=weight_source,
                    lot_reference=lot_reference, max_sellable=max_sellable)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.LINE_ADDED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id,
                       line_id=line.id, product_id=product_id)
        return SaleResult.ok("Línea agregada", entity_id=sale.id, operation_id=operation_id,
                             line_id=line.id, sale=SaleDTO.from_entity(sale))


class UpdateSaleLineQuantityUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, line_id: str, quantity: Decimal,
        actor_user_id: str, operation_id: str, quantity_unit: str = "PZA",
        max_sellable: Decimal | None = None,
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.LINE_UPDATE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            try:
                sale.update_line_quantity(line_id, Quantity(quantity, quantity_unit),
                                          max_sellable=max_sellable)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.LINE_UPDATED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id, line_id=line_id)
        return SaleResult.ok("Cantidad actualizada", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class RemoveSaleLineUseCase(_SalesBaseUseCase):
    def execute(self, connection, *, sale_id: str, line_id: str, actor_user_id: str,
                operation_id: str) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.LINE_REMOVE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            try:
                sale.remove_line(line_id)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.LINE_REMOVED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id, line_id=line_id)
        return SaleResult.ok("Línea eliminada", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class AssignCustomerToSaleUseCase(_SalesBaseUseCase):
    """No dedicated `SalesPermissions` code exists for "assign customer" —
    neither this repo's catalog nor the master prompt's own §61 list names
    one. Gated under `SALE_CREATE` (customer assignment is part of composing
    the sale before checkout, the closest existing code) rather than
    inventing a new permission in a phase scoped to Commands/Queries/
    UseCases/DTO/Authorization wiring, not catalog expansion.

    SALES-10: now validates the customer actually exists in Customer Master
    before assigning (`SalesCustomerClient.exists`) — until this phase,
    `sale.assign_customer(customer_id)` accepted any UUIDv7-shaped string
    with zero existence check, a real gap found while building the
    search/quick-create/card-scan flows that all produce a real Customer
    Master id this use case should now actually verify."""

    def execute(self, connection, *, sale_id: str, customer_id: str | None,
                actor_user_id: str, operation_id: str) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_CREATE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        if customer_id is not None:
            from backend.infrastructure.integrations.sales_customer_client import (
                SalesCustomerClient,
            )
            if not SalesCustomerClient(connection).exists(customer_id):
                return fail_from_domain_error(
                    SaleCustomerNotFoundError(f"Cliente {customer_id} no existe"),
                    operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            try:
                sale.assign_customer(customer_id)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.CUSTOMER_ASSIGNED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id, customer_id=customer_id)
        return SaleResult.ok("Cliente asignado", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))
