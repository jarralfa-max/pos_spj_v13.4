"""Count use cases (INV-13): create → record → confirm → approve (§27-28).

The expected quantity is snapshotted from the balance at creation and stored, but
never exposed during a blind count — capture happens without it; the variance
(counted − expected) is computed only on confirm, after which the count is locked.
A confirmed count with variance goes to approval, where the counter may not
approve their own (segregation of duties).
"""

from __future__ import annotations

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.domain.inventory.entities.count import (
    InventoryCount,
    InventoryCountLine,
)
from backend.domain.inventory.enums import CountType, InventoryStatus
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


def _emit(uow, event_name, count, *, operation_id, actor_user_id, **extra):
    payload = build_event_payload(
        event_name, operation_id=operation_id, entity_id=count.id,
        branch_id=count.branch_id, warehouse_id=count.warehouse_id,
        user_id=actor_user_id, folio=count.folio, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


def _fail(exc, operation_id):
    code = ("PERMISSION_DENIED" if isinstance(exc, InventoryPermissionDeniedError)
            else "SEGREGATION_OF_DUTIES" if isinstance(exc, SegregationOfDutiesError)
            else "INVENTORY_RULE_VIOLATION")
    return InventoryResult.fail(str(exc), code, operation_id=operation_id)


class CreateCountUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, folio: str, count_type: CountType, branch_id: str,
                warehouse_id: str, scope_lines: list[dict], operation_id: str,
                actor_user_id: str, blind: bool = True) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.COUNT_CREATE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                lines = []
                for item in scope_lines:
                    bal = uow.balances.get(
                        product_id=str(item["product_id"]), branch_id=branch_id,
                        warehouse_id=warehouse_id,
                        inventory_status=InventoryStatus.AVAILABLE,
                        location_id=item.get("location_id"), lot_id=item.get("lot_id"))
                    lines.append(InventoryCountLine.create(
                        product_id=str(item["product_id"]),
                        expected_quantity=bal.quantity if bal else 0,
                        expected_weight=bal.weight if bal else 0,
                        location_id=item.get("location_id"), lot_id=item.get("lot_id")))
                count = InventoryCount.create(
                    folio=folio, count_type=count_type, branch_id=branch_id,
                    warehouse_id=warehouse_id, lines=lines, blind=blind,
                    created_by_user_id=actor_user_id)
                count.plan()
                count.start()
                uow.counts.save(count)
                _emit(uow, InventoryEvents.INVENTORY_COUNT_STARTED, count,
                      operation_id=operation_id, actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Conteo iniciado", entity_id=count.id,
                                  operation_id=operation_id,
                                  line_ids=[l.id for l in count.lines])


class RecordCountUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, count_id: str, line_id: str, counted_quantity,
                operation_id: str, actor_user_id: str, counted_weight=0) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.COUNT_EXECUTE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                count = uow.counts.get(count_id)
                if count is None:
                    return InventoryResult.fail("Conteo no encontrado", "COUNT_NOT_FOUND",
                                                operation_id=operation_id)
                count.record(line_id, counted_quantity=counted_quantity,
                             counted_weight=counted_weight)
                if not count.counted_by_user_id:
                    count.counted_by_user_id = actor_user_id
                uow.counts.save(count)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Conteo capturado", entity_id=count_id,
                                  operation_id=operation_id)


class ConfirmCountUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, count_id: str, operation_id: str,
                actor_user_id: str) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.COUNT_CONFIRM)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                count = uow.counts.get(count_id)
                if count is None:
                    return InventoryResult.fail("Conteo no encontrado", "COUNT_NOT_FOUND",
                                                operation_id=operation_id)
                count.confirm()
                _emit(uow, InventoryEvents.INVENTORY_COUNT_CONFIRMED, count,
                      operation_id=operation_id, actor_user_id=actor_user_id)
                if count.has_variance:
                    count.mark_pending_approval()
                    _emit(uow, InventoryEvents.INVENTORY_COUNT_VARIANCE_DETECTED, count,
                          operation_id=f"{operation_id}:var", actor_user_id=actor_user_id)
                uow.counts.save(count)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Conteo confirmado", entity_id=count_id,
                                  operation_id=operation_id, status=count.status.value,
                                  has_variance=count.has_variance)


class ApproveCountUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()
        self._segregation = SegregationOfDutiesPolicy()

    def execute(self, connection, *, count_id: str, operation_id: str,
                actor_user_id: str) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.COUNT_APPROVE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                count = uow.counts.get(count_id)
                if count is None:
                    return InventoryResult.fail("Conteo no encontrado", "COUNT_NOT_FOUND",
                                                operation_id=operation_id)
                self._segregation.enforce_counter_not_self_approving_critical(
                    count.counted_by_user_id or "", actor_user_id,
                    is_critical=count.has_variance)
                count.approve(user_id=actor_user_id)
                uow.counts.save(count)
        except (InventoryDomainError, SegregationOfDutiesError) as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Conteo aprobado", entity_id=count_id,
                                  operation_id=operation_id)
