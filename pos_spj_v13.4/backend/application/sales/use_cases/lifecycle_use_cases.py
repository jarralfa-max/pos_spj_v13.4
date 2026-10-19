"""Sale lifecycle use cases: suspend, resume, cancel, begin checkout.

No shared `_TransitionUseCase` hook (unlike customers' — see
lifecycle_use_cases.py there) because Suspend/Resume each need
cross-aggregate data (`uow.sales.count_suspended(...)`) fetched BEFORE
calling the entity method, which customers' uniform `_apply(entity, reason)`
hook shape doesn't accommodate. Written explicitly, same discipline
cash_register's own `OpenCashShiftUseCase` already uses when a transition
needs more than a bare reason string.

`CompleteSaleUseCase` (CHECKOUT_PENDING/PAYMENT_PENDING -> COMPLETED) is
deliberately NOT built here — it depends on real payment confirmation
(master prompt POS-13/14), which doesn't exist yet. `begin_checkout()` is
the boundary this phase can support honestly: it proves the sale is
checkout-ready (has lines, positive total) without pretending payment is
solved.

SALES-9/POS-9: `SuspendSaleUseCase` now reserves inventory before
transitioning to SUSPENDED, and `CancelSaleUseCase` releases it — this
mirrors the REAL existing behavior already live in
`modulos/ventas.py::suspender_venta`/`cancelar_venta` (confirmed in
SALES-0's audit: suspend already calls `StockReservationService.reservar()`
today), not the master prompt's more abstract "reserve on add-line" framing
in §20's own flow diagram. Reserving the whole current cart atomically at
suspend-time is what this codebase actually does; POS-9 wires the SAME real
behavior onto the new `Sale` aggregate instead of inventing a different one.
"""

from __future__ import annotations

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.application.sales.use_cases.payment_void_use_cases import _PaymentCompensation
from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import (
    InventoryShortageError,
    SalesDomainError,
    SaleNotFoundError,
)
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork


class SuspendSaleUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, actor_user_id: str, operation_id: str,
        max_suspended_sales: int, workstation_id: str | None = None,
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_SUSPEND)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale, denied = self._load_sale(uow, sale_id, actor_user_id, operation_id)
            if denied is not None:
                return denied
            current_suspended_count = uow.sales.count_suspended(
                branch_id=sale.branch_id, workstation_id=workstation_id)
            try:
                sale.suspend(
                    current_suspended_count=current_suspended_count,
                    max_suspended_sales=max_suspended_sales,
                    suspended_by_user_id=actor_user_id, workstation_id=workstation_id)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            if not sale.inventory_reservation_id:
                client = self._inventory_client(
                    connection, branch_id=sale.branch_id, actor_user_id=actor_user_id)
                try:
                    sale.inventory_reservation_id = client.reserve_for_sale(sale)
                except InventoryShortageError:
                    # Decisión del usuario (2026-10-02): con faltante sí se
                    # suspende, apartando lo que haya; la autorización de venta
                    # sin existencia se pide al cobrar, como en cualquier venta.
                    try:
                        sale.inventory_reservation_id = client.reserve_available_for_sale(sale)
                    except SalesDomainError as exc:
                        return fail_from_domain_error(exc, operation_id=operation_id)
                except SalesDomainError as exc:
                    return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.SUSPENDED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id)
        return SaleResult.ok("Venta suspendida", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class ResumeSaleUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, actor_user_id: str, operation_id: str,
        resuming_workstation_id: str | None = None,
        allow_cross_user_resume: bool = True, allow_cross_workstation_resume: bool = True,
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_RESUME)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale, denied = self._load_sale(uow, sale_id, actor_user_id, operation_id)
            if denied is not None:
                return denied
            try:
                sale.resume(
                    resuming_user_id=actor_user_id,
                    resuming_workstation_id=resuming_workstation_id,
                    allow_cross_user_resume=allow_cross_user_resume,
                    allow_cross_workstation_resume=allow_cross_workstation_resume)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.RESUMED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id)
        return SaleResult.ok("Venta reanudada", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class CancelSaleUseCase(_PaymentCompensation):
    """Cancelar ANTES de cobrar. Con pagos ya registrados (auditoría V02,
    decisión del usuario "compensar y avisar") anula cada uno en la misma
    transacción — CxC y vales se compensan solos — y devuelve en `refunds` lo
    que el cajero tiene que regresar al cliente. Nunca CANCELLED con dinero o
    deuda vivos (el dominio lo prohíbe)."""

    def execute(self, connection, *, sale_id: str, reason: str, actor_user_id: str,
                operation_id: str) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_CANCEL)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale, denied = self._load_sale(uow, sale_id, actor_user_id, operation_id)
            if denied is not None:
                return denied
            refunds: list[dict] = []
            try:
                for payment in list(sale.payments):
                    refunds.append(self._void_and_compensate(
                        connection, uow, sale, payment.id,
                        reason=f"Venta cancelada: {reason}", actor_user_id=actor_user_id,
                        operation_id=operation_id))
                sale.cancel(reason)
            except SalesDomainError as exc:
                uow.rollback()
                return fail_from_domain_error(exc, operation_id=operation_id)
            except Exception as exc:  # noqa: BLE001 - Finanzas/Fidelidad: se deshace todo
                uow.rollback()
                return SaleResult.fail(f"No se pudo cancelar: {exc}", "CANCEL_FAILED",
                                       operation_id=operation_id)
            if sale.inventory_reservation_id:
                client = self._inventory_client(
                    connection, branch_id=sale.branch_id, actor_user_id=actor_user_id)
                client.release(sale.inventory_reservation_id, reason="cancelada")
                sale.inventory_reservation_id = None
            uow.sales.save(sale)
            # `customer_id`: Fidelidad devuelve lo canjeado en esta venta.
            self._emit(uow, SaleEvents.CANCELLED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id, reason=reason,
                       customer_id=sale.customer_id,
                       loyalty_redeemed=str(sale.loyalty_redeemed_amount))
        return SaleResult.ok("Venta cancelada", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale), refunds=refunds)


class BeginSaleCheckoutUseCase(_SalesBaseUseCase):
    def execute(self, connection, *, sale_id: str, actor_user_id: str,
                operation_id: str) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_COMPLETE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale, denied = self._load_sale(uow, sale_id, actor_user_id, operation_id)
            if denied is not None:
                return denied
            if sale.status in (SaleStatus.CHECKOUT_PENDING, SaleStatus.PAYMENT_PENDING):
                # Auditoría V03: el cobro ya estaba abierto (se cerró la ventana
                # a medio cobrar). Se RETOMA con sus pagos, no se rechaza.
                return SaleResult.ok("Cobro en curso", entity_id=sale.id,
                                     operation_id=operation_id, resumed=True,
                                     sale=SaleDTO.from_entity(sale))
            try:
                sale.begin_checkout()
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.CHECKOUT_STARTED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id)
        return SaleResult.ok("Cobro iniciado", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale))


class ReturnSaleToCartUseCase(_SalesBaseUseCase):
    """Cerrar el cobro sin pagos regresa la venta al carrito (auditoría V03):
    antes `CHECKOUT_PENDING` no tenía vuelta y el carrito quedaba congelado."""

    def execute(self, connection, *, sale_id: str, actor_user_id: str,
                operation_id: str) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_COMPLETE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with SalesUnitOfWork(connection) as uow:
            sale, denied = self._load_sale(uow, sale_id, actor_user_id, operation_id)
            if denied is not None:
                return denied
            if sale.status is SaleStatus.ACTIVE:
                return SaleResult.ok("La venta ya está en el carrito", entity_id=sale.id,
                                     operation_id=operation_id, sale=SaleDTO.from_entity(sale))
            try:
                sale.return_to_cart()
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.RETURNED_TO_CART, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id)
        return SaleResult.ok("Venta de vuelta en el carrito", entity_id=sale.id,
                             operation_id=operation_id, sale=SaleDTO.from_entity(sale))
