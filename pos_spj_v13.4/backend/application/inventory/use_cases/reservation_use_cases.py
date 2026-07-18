"""Reservation use cases (INV-10): create, release, allocate lots (§22).

A reservation reduces available-to-promise on the AVAILABLE balance without
moving physical stock; releasing gives it back. Allocation binds a confirmed
reservation to specific lots via the FEFO LotAllocationService. Idempotent by
operation_id.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
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
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.domain.inventory.services.lot_allocation_service import (
    LotAllocationService,
    LotCandidate,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


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
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, product_id: str, branch_id: str, warehouse_id: str,
                source: ReservationSource, source_document_id: str, quantity,
                operation_id: str, actor_user_id: str, weight=0, expires_at=None,
                location_id: str | None = None, lot_id: str | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.RESERVATION_CREATE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
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
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, reservation_id: str, operation_id: str,
                actor_user_id: str, reason: str = "") -> InventoryResult:
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
        self._auth = authorization or InventoryAuthorizationPolicy()
        self._allocator = LotAllocationService()

    def execute(self, connection, *, reservation_id: str, operation_id: str,
                actor_user_id: str,
                strategy: AllocationStrategy = AllocationStrategy.FEFO) -> InventoryResult:
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
