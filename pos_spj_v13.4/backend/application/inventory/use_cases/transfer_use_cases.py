"""Transfer use cases (INV-12): create → approve → dispatch → receive (§24-25).

§24 stock rule: dispatch decreases the origin (TRANSFER_DISPATCH) and the quantity
is IN_TRANSIT (held on the transfer); the destination gains AVAILABLE stock only
on receipt (TRANSFER_RECEIPT). Segregation: the dispatcher may not confirm the
destination receipt. Stock movement and transfer state commit in one UnitOfWork.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.services.movement_posting import post_movement
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.entities.transfer import (
    InventoryTransfer,
    InventoryTransferLine,
)
from backend.domain.inventory.enums import MovementType, TransferStatus
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
    SegregationOfDutiesError,
)
from backend.domain.inventory.policies.segregation_of_duties_policy import (
    SegregationOfDutiesPolicy,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


def _emit(uow, event_name, transfer, *, operation_id, actor_user_id, **extra):
    payload = build_event_payload(
        event_name, operation_id=operation_id, entity_id=transfer.id,
        branch_id=transfer.origin_branch_id, warehouse_id=transfer.origin_warehouse_id,
        user_id=actor_user_id, folio=transfer.folio, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


def _fail(exc, operation_id):
    code = ("PERMISSION_DENIED" if isinstance(exc, InventoryPermissionDeniedError)
            else "SEGREGATION_OF_DUTIES" if isinstance(exc, SegregationOfDutiesError)
            else "INVENTORY_RULE_VIOLATION")
    return InventoryResult.fail(str(exc), code, operation_id=operation_id)


class CreateTransferUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, folio: str, origin_branch_id: str,
                origin_warehouse_id: str, destination_branch_id: str,
                destination_warehouse_id: str, lines: list[dict], operation_id: str,
                actor_user_id: str, auto_submit: bool = True) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.TRANSFER_CREATE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            transfer = InventoryTransfer.create(
                folio=folio, origin_branch_id=origin_branch_id,
                origin_warehouse_id=origin_warehouse_id,
                destination_branch_id=destination_branch_id,
                destination_warehouse_id=destination_warehouse_id,
                created_by_user_id=actor_user_id,
                lines=[InventoryTransferLine.create(
                    product_id=str(ln["product_id"]), quantity=ln["quantity"],
                    weight=ln.get("weight", 0), unit=ln.get("unit", "PZA"),
                    lot_id=ln.get("lot_id")) for ln in lines])
            if auto_submit:
                transfer.submit()
            with InventoryUnitOfWork(connection) as uow:
                uow.transfers.save(transfer)
                _emit(uow, InventoryEvents.INVENTORY_TRANSFER_CREATED, transfer,
                      operation_id=operation_id, actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Transferencia creada", entity_id=transfer.id,
                                  operation_id=operation_id)


class ApproveTransferUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, transfer_id: str, operation_id: str,
                actor_user_id: str) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.TRANSFER_APPROVE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                transfer = uow.transfers.get(transfer_id)
                if transfer is None:
                    return InventoryResult.fail("Transferencia no encontrada",
                                                "TRANSFER_NOT_FOUND",
                                                operation_id=operation_id)
                transfer.approve(user_id=actor_user_id)
                uow.transfers.save(transfer)
                _emit(uow, InventoryEvents.INVENTORY_TRANSFER_APPROVED, transfer,
                      operation_id=operation_id, actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Transferencia aprobada", entity_id=transfer_id,
                                  operation_id=operation_id)


class DispatchTransferUseCase:
    """Pick + ready + dispatch: decrease the origin and put stock IN_TRANSIT (§24)."""

    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, transfer_id: str, operation_id: str,
                actor_user_id: str, carrier: str | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.TRANSFER_DISPATCH)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                transfer = uow.transfers.get(transfer_id)
                if transfer is None:
                    return InventoryResult.fail("Transferencia no encontrada",
                                                "TRANSFER_NOT_FOUND",
                                                operation_id=operation_id)
                if transfer.status is TransferStatus.IN_TRANSIT:
                    return InventoryResult.ok("Transferencia ya despachada (idempotente)",
                                              entity_id=transfer_id,
                                              operation_id=operation_id,
                                              already_processed=True)
                # decrease origin AVAILABLE (stock leaves origin)
                movement = InventoryMovement.create(
                    movement_type=MovementType.TRANSFER_DISPATCH,
                    branch_id=transfer.origin_branch_id,
                    warehouse_id=transfer.origin_warehouse_id, source_module="inventory",
                    source_document_type="TRANSFER", source_document_id=transfer.id,
                    operation_id=f"{operation_id}:dispatch", created_by_user_id=actor_user_id,
                    lines=[InventoryMovementLine.create(
                        product_id=line.product_id, quantity=line.quantity,
                        weight=line.weight, unit=line.unit, lot_id=line.lot_id,
                        from_location_id=transfer.origin_warehouse_id)
                        for line in transfer.lines])
                post_movement(uow, movement, actor_user_id=actor_user_id)
                # walk picking → ready → in transit
                if transfer.status is TransferStatus.APPROVED:
                    transfer.start_picking()
                if transfer.status is TransferStatus.PICKING:
                    transfer.ready()
                transfer.dispatch(user_id=actor_user_id, carrier=carrier)
                uow.transfers.save(transfer)
                _emit(uow, InventoryEvents.INVENTORY_TRANSFER_DISPATCHED, transfer,
                      operation_id=operation_id, actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Transferencia despachada", entity_id=transfer_id,
                                  operation_id=operation_id)


class ReceiveTransferUseCase:
    """Receive at destination: increase AVAILABLE for accepted qty, record differences."""

    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()
        self._segregation = SegregationOfDutiesPolicy()

    def execute(self, connection, *, transfer_id: str, received: dict, operation_id: str,
                actor_user_id: str) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.TRANSFER_RECEIVE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                transfer = uow.transfers.get(transfer_id)
                if transfer is None:
                    return InventoryResult.fail("Transferencia no encontrada",
                                                "TRANSFER_NOT_FOUND",
                                                operation_id=operation_id)
                self._segregation.enforce_dispatcher_not_receiver(
                    transfer.dispatched_by_user_id or "", actor_user_id)

                accepted_lines = [
                    InventoryMovementLine.create(
                        product_id=line.product_id, quantity=Decimal(str(received[line.id])),
                        weight=line.weight, unit=line.unit, lot_id=line.lot_id,
                        to_location_id=transfer.destination_warehouse_id)
                    for line in transfer.lines
                    if Decimal(str(received.get(line.id, 0))) > 0]
                if accepted_lines:
                    movement = InventoryMovement.create(
                        movement_type=MovementType.TRANSFER_RECEIPT,
                        branch_id=transfer.destination_branch_id,
                        warehouse_id=transfer.destination_warehouse_id,
                        source_module="inventory", source_document_type="TRANSFER",
                        source_document_id=transfer.id,
                        operation_id=f"{operation_id}:receipt",
                        created_by_user_id=actor_user_id, lines=accepted_lines)
                    post_movement(uow, movement, actor_user_id=actor_user_id)

                transfer.receive(user_id=actor_user_id,
                                 received={k: Decimal(str(v)) for k, v in received.items()})
                uow.transfers.save(transfer)
                _emit(uow, InventoryEvents.INVENTORY_TRANSFER_RECEIVED, transfer,
                      operation_id=operation_id, actor_user_id=actor_user_id,
                      status=transfer.status.value)
                if transfer.status is TransferStatus.WITH_DIFFERENCES:
                    _emit(uow, InventoryEvents.INVENTORY_TRANSFER_DIFFERENCE_DETECTED,
                          transfer, operation_id=f"{operation_id}:diff",
                          actor_user_id=actor_user_id)
        except (InventoryDomainError, SegregationOfDutiesError) as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok(f"Transferencia {transfer.status.value}",
                                  entity_id=transfer_id, operation_id=operation_id,
                                  status=transfer.status.value)
