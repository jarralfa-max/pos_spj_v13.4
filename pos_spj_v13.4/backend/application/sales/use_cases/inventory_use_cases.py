"""Inventory-reservation use cases (master prompt §20, POS-9). Each wraps
`SalesInventoryClient` (which wraps the real, legacy `StockReservationService`
SALES-0 already classified REUSE) — Sales never touches inventory tables
itself (§6).

`ReserveInventoryForSaleUseCase` is idempotent at the use-case level: if
`sale.inventory_reservation_id` is already set, it returns the existing
reservation instead of creating a second one (the underlying
`stock_reservas.folio` UNIQUE constraint would reject a duplicate `sale.id`
anyway — this check just avoids surfacing that as an error).

`ConfirmInventoryReservationUseCase`/`ExpireOrphanedInventoryReservationsUseCase`
are built as the standalone actions §64/§20 name, ready for a future
checkout-completion phase (POS-13/14) and an administrative sweep to call —
neither is wired into another use case yet (see this phase's own
docs/refactor/SALES-9_reservas_inventario.md for what IS wired: Reserve into
SuspendSaleUseCase, Release into CancelSaleUseCase, matching the REAL
existing legacy behavior `modulos/ventas.py::suspender_venta`/`cancelar_venta`
already have, not just the master prompt's abstract flow).
"""

from __future__ import annotations

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.exceptions import SalesDomainError, SaleNotFoundError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_inventory_client import SalesInventoryClient


class ReserveInventoryForSaleUseCase(_SalesBaseUseCase):
    def execute(self, connection, *, sale_id: str, actor_user_id: str,
                operation_id: str) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_SUSPEND)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            if sale.inventory_reservation_id:
                return SaleResult.ok(
                    "La venta ya tiene una reserva activa", entity_id=sale.id,
                    operation_id=operation_id, sale=SaleDTO.from_entity(sale),
                    reservation_id=sale.inventory_reservation_id)
            client = SalesInventoryClient(connection, branch_id=sale.branch_id)
            try:
                reservation_id = client.reserve_for_sale(sale)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            sale.inventory_reservation_id = reservation_id
            uow.sales.save(sale)
        return SaleResult.ok("Inventario reservado", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale), reservation_id=reservation_id)


class ConfirmInventoryReservationUseCase(_SalesBaseUseCase):
    def execute(self, connection, *, sale_id: str, actor_user_id: str,
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
            if not sale.inventory_reservation_id:
                return SaleResult.ok(
                    "La venta no tiene reserva de inventario que confirmar",
                    entity_id=sale.id, operation_id=operation_id,
                    sale=SaleDTO.from_entity(sale))
            client = SalesInventoryClient(connection, branch_id=sale.branch_id)
            try:
                client.confirm(sale.inventory_reservation_id, sale_id=sale.id,
                               folio=sale.sale_number or sale.id)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
        return SaleResult.ok("Reserva confirmada", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class ReleaseInventoryReservationUseCase(_SalesBaseUseCase):
    def execute(self, connection, *, sale_id: str, actor_user_id: str, operation_id: str,
                reason: str = "cancelada") -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_CANCEL)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)
            if not sale.inventory_reservation_id:
                return SaleResult.ok(
                    "La venta no tiene reserva de inventario que liberar",
                    entity_id=sale.id, operation_id=operation_id,
                    sale=SaleDTO.from_entity(sale))
            client = SalesInventoryClient(connection, branch_id=sale.branch_id)
            client.release(sale.inventory_reservation_id, reason=reason)
            sale.inventory_reservation_id = None
            uow.sales.save(sale)
        return SaleResult.ok("Reserva liberada", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class ExpireOrphanedInventoryReservationsUseCase:
    """A system sweep (§41's orphan-expiry requirement), not a per-sale user
    action — no `SalesPermissions` check the way the other three use cases
    have, same reasoning this repo already applies to other sweep-style
    entry points (e.g. CRM's time-based automation trigger sweep): it's a
    callable maintenance hook, not gated as if a cashier were invoking it
    directly. Branch-scoped because `StockReservationService` itself is
    constructed per-branch."""

    def execute(self, connection, *, branch_id: str) -> int:
        """Does NOT commit — matches every other component in this stack
        (repositories/UoW own the transaction boundary, never a bare use
        case); the caller commits `connection` once this returns."""
        client = SalesInventoryClient(connection, branch_id=branch_id)
        return client.expire_orphaned()
