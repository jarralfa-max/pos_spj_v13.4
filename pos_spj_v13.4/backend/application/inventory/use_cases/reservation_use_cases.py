"""Reservation use cases (INV-10): create, release, allocate lots (§22).

A reservation reduces available-to-promise on the AVAILABLE balance without
moving physical stock; releasing gives it back. Allocation binds a confirmed
reservation to specific lots via the FEFO LotAllocationService. Idempotent by
operation_id.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.domain.inventory.entities.reservation import (
    InventoryAllocation,
    InventoryReservation,
)
from backend.domain.inventory.enums import (
    AllocationStrategy,
    InventoryStatus,
    LotQualityStatus,
    ReservationSource,
    ReservationStatus,
)
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    BranchScopeError,
    InventoryDomainError,
    InventoryPermissionDeniedError,
    WarehouseScopeError,
)
from backend.domain.inventory.services.lot_allocation_service import (
    LotAllocationService,
    LotCandidate,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


def _utcnow_iso() -> str:
    """Mismo formato que `InventoryReservation.is_expired()` compara.

    La comparación de vencimiento es textual (`now >= expires_at`), así que un
    formato distinto —con microsegundos, o sin zona— ordenaría mal y las
    reservas caducarían antes o nunca.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _scope_fail(context, branch_id, warehouse_id, operation_id):
    """§5.3: valida sucursal/almacén contra el alcance del actor. Devuelve un
    InventoryResult SCOPE_DENIED o None si el alcance es válido / no hay contexto."""
    if context is None:
        return None
    try:
        context.enforce_branch(branch_id)
        context.enforce_warehouse(warehouse_id)
    except (BranchScopeError, WarehouseScopeError) as exc:
        return InventoryResult.fail(str(exc), "SCOPE_DENIED",
                                    operation_id=operation_id)
    return None


def _emit(uow, event_name, *, operation_id, entity_id, product_id=None, branch_id=None,
          warehouse_id=None, actor_user_id=None, **extra):
    payload = build_event_payload(
        event_name, operation_id=operation_id, entity_id=entity_id,
        product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
        user_id=actor_user_id, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


class CreateReservationUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, product_id: str, branch_id: str, warehouse_id: str,
                source: ReservationSource, source_document_id: str, quantity,
                operation_id: str, actor_user_id: str, weight=0, expires_at=None,
                location_id: str | None = None, lot_id: str | None = None,
                context: InventoryExecutionContext | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.RESERVATION_CREATE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        # §5.3: la sucursal/almacén enviados por la UI se validan contra el alcance.
        denied = _scope_fail(context, branch_id, warehouse_id, operation_id)
        if denied is not None:
            return denied
        try:
            with InventoryUnitOfWork(connection) as uow:
                existing = uow.reservations.find_by_operation_id(operation_id)
                if existing is not None:
                    return InventoryResult.ok("Reserva ya registrada (idempotente)",
                                              entity_id=existing["id"],
                                              operation_id=operation_id,
                                              already_processed=True)
                balance = uow.balances.get(
                    product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
                    inventory_status=InventoryStatus.AVAILABLE, location_id=location_id,
                    lot_id=lot_id)
                if balance is None:
                    return InventoryResult.fail("Sin balance disponible para reservar",
                                                "INSUFFICIENT_AVAILABILITY",
                                                operation_id=operation_id)
                balance.reserve(quantity=Decimal(str(quantity)), weight=Decimal(str(weight)))
                uow.balances.upsert(balance)

                reservation = InventoryReservation.create(
                    product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
                    source=source, source_document_id=source_document_id,
                    operation_id=operation_id, quantity=quantity, weight=weight,
                    status=ReservationStatus.CONFIRMED, location_id=location_id,
                    lot_id=lot_id, expires_at=expires_at, created_by_user_id=actor_user_id)
                uow.reservations.save(reservation)
                uow.audit.record(entity_type="RESERVATION", entity_id=reservation.id,
                                 action="RESERVED", user_id=actor_user_id,
                                 operation_id=operation_id, product_id=product_id,
                                 branch_id=branch_id, warehouse_id=warehouse_id)
                _emit(uow, InventoryEvents.INVENTORY_RESERVED, operation_id=operation_id,
                      entity_id=reservation.id, product_id=product_id, branch_id=branch_id,
                      warehouse_id=warehouse_id, actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok("Reserva creada", entity_id=reservation.id,
                                  operation_id=operation_id)


class ReleaseReservationUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, reservation_id: str, operation_id: str,
                actor_user_id: str, reason: str = "",
                context: InventoryExecutionContext | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.RESERVATION_RELEASE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                reservation = uow.reservations.get(reservation_id)
                if reservation is None:
                    return InventoryResult.fail("Reserva no encontrada",
                                                "RESERVATION_NOT_FOUND",
                                                operation_id=operation_id)
                # §5.3: alcance validado contra la sucursal/almacén reales de la reserva.
                denied = _scope_fail(context, reservation.branch_id,
                                     reservation.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if not reservation.is_active:
                    return InventoryResult.ok("Reserva ya inactiva (idempotente)",
                                              entity_id=reservation_id,
                                              operation_id=operation_id,
                                              already_processed=True)
                balance = uow.balances.get(
                    product_id=reservation.product_id, branch_id=reservation.branch_id,
                    warehouse_id=reservation.warehouse_id,
                    inventory_status=InventoryStatus.AVAILABLE,
                    location_id=reservation.location_id, lot_id=reservation.lot_id)
                if balance is not None:
                    balance.release_reservation(quantity=reservation.quantity,
                                                weight=reservation.weight)
                    uow.balances.upsert(balance)
                reservation.release()
                uow.reservations.update_status(reservation.id, reservation.status)
                uow.audit.record(entity_type="RESERVATION", entity_id=reservation.id,
                                 action="RELEASED", user_id=actor_user_id,
                                 operation_id=operation_id, reason=reason,
                                 product_id=reservation.product_id)
                _emit(uow, InventoryEvents.INVENTORY_RESERVATION_RELEASED,
                      operation_id=operation_id, entity_id=reservation.id,
                      product_id=reservation.product_id, branch_id=reservation.branch_id,
                      actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok("Reserva liberada", entity_id=reservation_id,
                                  operation_id=operation_id)


class AllocateReservationUseCase:
    """Bind a confirmed reservation to specific lots via FEFO (§22)."""

    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()
        self._allocator = LotAllocationService()

    def execute(self, connection, *, reservation_id: str, operation_id: str,
                actor_user_id: str,
                strategy: AllocationStrategy = AllocationStrategy.FEFO,
                context: InventoryExecutionContext | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.RESERVATION_CREATE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                reservation = uow.reservations.get(reservation_id)
                if reservation is None:
                    return InventoryResult.fail("Reserva no encontrada",
                                                "RESERVATION_NOT_FOUND",
                                                operation_id=operation_id)
                # §5.3: alcance validado contra la sucursal/almacén reales de la reserva.
                denied = _scope_fail(context, reservation.branch_id,
                                     reservation.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                candidates = self._lot_candidates(uow, reservation)
                plan = self._allocator.allocate(candidates, reservation.quantity,
                                                strategy=strategy)
                for alloc in plan:
                    uow.reservations.save_allocation(InventoryAllocation.create(
                        reservation_id=reservation.id, quantity=alloc.quantity,
                        lot_id=alloc.lot_id))
                reservation.mark_allocated()
                uow.reservations.update_status(reservation.id, reservation.status)
                _emit(uow, InventoryEvents.INVENTORY_ALLOCATED, operation_id=operation_id,
                      entity_id=reservation.id, product_id=reservation.product_id,
                      branch_id=reservation.branch_id, actor_user_id=actor_user_id,
                      lots=len(plan))
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok("Reserva asignada a lotes", entity_id=reservation_id,
                                  operation_id=operation_id, allocations=len(plan))

    def _lot_candidates(self, uow, reservation) -> list[LotCandidate]:
        lots = {row["id"]: row
                for row in uow.lots.list_for_product(reservation.product_id)}
        candidates: list[LotCandidate] = []
        for bal in uow.balances.list_by_product_branch(
                reservation.product_id, reservation.branch_id):
            if bal["inventory_status"] != InventoryStatus.AVAILABLE.value:
                continue
            # §22/§5.3: la reserva se creó contra un almacén concreto y decrementó
            # SU balance; la asignación debe quedarse en ese mismo almacén — nunca
            # ligar un lote físicamente en otro almacén (fuga inter-almacén).
            if bal["warehouse_id"] != reservation.warehouse_id:
                continue
            if not bal["lot_id"]:
                continue
            available = (self._to_decimal(bal["quantity"])
                         - self._to_decimal(bal["reserved_quantity"]))
            lot = lots.get(bal["lot_id"])
            candidates.append(LotCandidate(
                lot_id=bal["lot_id"], available_quantity=available,
                expiration_date=lot["expiration_date"] if lot else None,
                quality_status=(LotQualityStatus(lot["quality_status"]) if lot
                                else LotQualityStatus.RELEASED)))
        return candidates

    @staticmethod
    def _to_decimal(value):
        return Decimal(str(value)) if value not in (None, "") else Decimal("0")


class FulfillReservationUseCase:
    """Marca una reserva como CUMPLIDA: el documento origen se completó.

    NO ES LO MISMO QUE LIBERAR, y la diferencia es la parte que importa:

      liberar  -> la operación se canceló. La retención se deshace y la
                  mercancía vuelve a estar disponible para vender.
      cumplir  -> la venta se completó. La mercancía SALIÓ. La retención se
                  mantiene, porque soltarla haría que lo ya vendido volviera a
                  aparecer como disponible en el punto de venta.

    POR QUÉ NO SE DESCUENTA LA EXISTENCIA AQUÍ. Lo coherente sería que al
    cumplirse la reserva se registrara además un movimiento de inventario de
    tipo venta que bajara la existencia real, y entonces sí soltar la
    retención. No se hace, y no es un olvido: hoy NINGUNA parte del sistema
    registra ese movimiento al completar una venta (verificado: no existe un
    solo uso de `MovementType.SALE` en todo el repositorio), mientras que las
    devoluciones sí reponen con `SALE_RETURN`. Hacerlo aquí cambiaría la
    valuación del inventario y el costo de ventas, que es una decisión del
    negocio y no de una migración de código.

    Manteniendo la retención, el número de "reservado" acumula exactamente lo
    vendido y no descontado: el síntoma queda visible y medible en lugar de
    disolverse. Ver la nota de este hallazgo en
    `backend/infrastructure/integrations/sales_inventory_client.py`.
    """

    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, reservation_id: str, operation_id: str,
                actor_user_id: str,
                context: InventoryExecutionContext | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.RESERVATION_CREATE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                reservation = uow.reservations.get(reservation_id)
                if reservation is None:
                    return InventoryResult.fail("Reserva no encontrada",
                                                "RESERVATION_NOT_FOUND",
                                                operation_id=operation_id)
                denied = _scope_fail(context, reservation.branch_id,
                                     reservation.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if not reservation.is_active:
                    return InventoryResult.ok("Reserva ya inactiva (idempotente)",
                                              entity_id=reservation_id,
                                              operation_id=operation_id,
                                              already_processed=True)
                uow.reservations.update_status(reservation.id, ReservationStatus.FULFILLED)
                uow.audit.record(entity_type="RESERVATION", entity_id=reservation.id,
                                 action="FULFILLED", user_id=actor_user_id,
                                 operation_id=operation_id,
                                 product_id=reservation.product_id,
                                 branch_id=reservation.branch_id,
                                 warehouse_id=reservation.warehouse_id)
                _emit(uow, InventoryEvents.INVENTORY_RESERVATION_FULFILLED,
                      operation_id=operation_id, entity_id=reservation.id,
                      product_id=reservation.product_id, branch_id=reservation.branch_id,
                      actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok("Reserva cumplida", entity_id=reservation_id,
                                  operation_id=operation_id)


class ExpireReservationsUseCase:
    """Caduca las reservas vencidas y devuelve la mercancía a disponible.

    Una reserva vencida es una operación que quedó a medias — una venta
    suspendida que nadie retomó, por ejemplo. Su mercancía tiene que volver a
    venderse, así que aquí SÍ se suelta la retención: caducar es una forma de
    liberar, no de cumplir.

    Devuelve cuántas caducó. Cero es el resultado normal.
    """

    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, operation_id: str, actor_user_id: str,
                now: str | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.RESERVATION_RELEASE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        momento = now or _utcnow_iso()
        caducadas = 0
        try:
            with InventoryUnitOfWork(connection) as uow:
                for reservation in uow.reservations.list_active_expired(now=momento):
                    balance = uow.balances.get(
                        product_id=reservation.product_id, branch_id=reservation.branch_id,
                        warehouse_id=reservation.warehouse_id,
                        inventory_status=InventoryStatus.AVAILABLE,
                        location_id=reservation.location_id, lot_id=reservation.lot_id)
                    if balance is not None:
                        balance.release_reservation(quantity=reservation.quantity,
                                                    weight=reservation.weight)
                        uow.balances.upsert(balance)
                    uow.reservations.update_status(reservation.id, ReservationStatus.EXPIRED)
                    uow.audit.record(entity_type="RESERVATION", entity_id=reservation.id,
                                     action="EXPIRED", user_id=actor_user_id,
                                     operation_id=operation_id,
                                     product_id=reservation.product_id,
                                     branch_id=reservation.branch_id)
                    _emit(uow, InventoryEvents.INVENTORY_RESERVATION_EXPIRED,
                          operation_id=operation_id, entity_id=reservation.id,
                          product_id=reservation.product_id,
                          branch_id=reservation.branch_id, actor_user_id=actor_user_id)
                    caducadas += 1
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok(f"{caducadas} reservas caducadas",
                                  operation_id=operation_id, expired=caducadas)
