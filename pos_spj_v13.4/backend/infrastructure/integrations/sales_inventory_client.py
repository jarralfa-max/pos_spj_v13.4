"""SalesInventoryClient — Sales' own integration point onto Inventory
(master prompt §6/§20: "Ventas no es dueño de inventario"; §8.4 names
`inventory_client.py` as exactly this kind of adapter). Mirrors the shape of
`losses_inventory_gateway.py` (constructor-injected collaborator, thin
per-action methods) but wraps `core.services.stock_reservation_service.
StockReservationService` directly rather than a use case, since that's the
real, already-solid implementation SALES-0's audit classified REUSE.

`StockReservationService` is legacy: it takes `float` and Spanish dict keys
(`{"id": ..., "cantidad": ...}`), talks to the `stock_reservas`/
`stock_reserva_detalles` tables (REAL columns, not TEXT-decimal). This
client is the ONLY place in the new `backend/application/sales/` stack that
converts Decimal → float — never inside the domain, never inside a use
case — exactly at the boundary where Sales' Decimal-only world meets a
legacy float-typed table it doesn't own and isn't rebuilding here.
"""

from __future__ import annotations

from decimal import Decimal

from core.services.stock_reservation_service import StockReservationService

from backend.domain.sales.entities import Sale
from backend.domain.sales.exceptions import InventoryReservationFailedError


class SalesInventoryClient:
    def __init__(self, connection, *, branch_id: str) -> None:
        self._connection = connection
        self._branch_id = branch_id
        self._service = StockReservationService(connection, branch_id)

    def reserve_for_sale(self, sale: Sale) -> str:
        """§20: valida disponibilidad y reserva TODAS las líneas actuales de
        la venta de forma atómica (un SAVEPOINT dentro de
        StockReservationService.reservar). `stock_reservas.folio` es
        UNIQUE — usar `sale.id` (siempre UUIDv7, siempre presente) en vez de
        `sale.sale_number` (opcional) como folio evita colisiones por venta
        y da idempotencia real: reservar dos veces para la misma venta con
        el mismo `sale.id` viola la constraint UNIQUE de la tabla legacy."""
        items = [
            {"id": line.product_id, "cantidad": float(line.quantity.value)}
            for line in sale.lines
        ]
        try:
            return self._service.reservar(sale.id, items)
        except (ValueError, RuntimeError) as exc:
            raise InventoryReservationFailedError(str(exc)) from exc

    def confirm(self, reservation_id: str, *, sale_id: str, folio: str) -> None:
        try:
            self._service.confirmar(reservation_id, sale_id, folio)
        except RuntimeError as exc:
            raise InventoryReservationFailedError(str(exc)) from exc

    def release(self, reservation_id: str, *, reason: str = "cancelada") -> None:
        self._service.liberar(reservation_id, reason)

    def expire_orphaned(self) -> int:
        return self._service.expirar_huerfanas()

    def restore_for_return(
        self, *, product_id: str, quantity: Decimal, sale_id: str, operation_id: str,
        actor_user_id: str, reason_code: str, source_document_type: str,
    ) -> None:
        """POS-16/§42-44: puts returned/reversed goods back into sellable
        stock. Mirrors `core/services/sales_reversal_service.py::
        _post_canonical_return` exactly (confirmed via research to be the
        REAL, already-working canonical restoration path a legacy full
        cancellation already uses) — same `MovementType.SALE_RETURN`,
        `branch_id` reused as `warehouse_id` (this repo's own established
        simplification, not invented here), `InventoryStatus.AVAILABLE`.

        Unlike `SalesCashEffectsClient` (SALES-14), this DOES compose into
        the caller's own atomic transaction: `InventoryUnitOfWork` supports
        `owns_transaction=False`, so this call joins whatever
        `SalesUnitOfWork` the caller already has open — the first real
        composition of Sales' own SAVEPOINT with another bounded context's
        write, exactly what `SalesUnitOfWork`'s own docstring anticipated
        since SALES-5."""
        from backend.application.inventory.use_cases.post_inventory_movement import (
            PostInventoryMovementUseCase,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import InventoryStatus, MovementType
        from backend.domain.sales.exceptions import InventoryReservationFailedError as _Err

        line = InventoryMovementLine.create(
            product_id=product_id, quantity=quantity, to_location_id=self._branch_id,
            to_status=InventoryStatus.AVAILABLE, reason_code=reason_code)
        movement = InventoryMovement.create(
            movement_type=MovementType.SALE_RETURN, branch_id=self._branch_id,
            warehouse_id=self._branch_id, source_module="sales",
            source_document_type=source_document_type, source_document_id=str(sale_id),
            operation_id=str(operation_id), created_by_user_id=str(actor_user_id), lines=[line])
        result = PostInventoryMovementUseCase().execute(
            self._connection, movement, actor_user_id=str(actor_user_id),
            owns_transaction=False)
        if not result.success:
            raise _Err(result.message or "No se pudo restaurar inventario.")
