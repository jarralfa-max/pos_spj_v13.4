"""ResolveTemperatureExcursionUseCase (INV-9, §21) — close an open excursion.

Inventory only records cold-chain facts; Quality decides release or disposal
(same split already documented on ``RecordTemperatureReadingUseCase`` and the
domain entities). When an excursion auto-blocked a lot (``action_taken=
QUARANTINE`` — a direct ``quality_status=QUARANTINED`` transition, not a real
``InventoryQuarantine`` row), resolving it delegates the lot-side decision to
the existing ``SetLotQualityStatusUseCase`` (RELEASE → back to available, REJECT
→ written off) instead of duplicating its stock-bucket projection — the same
"compose two existing use cases" shape as ``RecordCatchWeightUseCase`` (INV-8).
Marking the excursion itself resolved is this use case's own increment.
"""

from __future__ import annotations

import json
from typing import Literal

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.use_cases.lot_use_cases import (
    SetLotQualityStatusUseCase,
)
from backend.domain.inventory.enums import LotQualityStatus
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
    WarehouseScopeError,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)

_RESOLUTION_STATUS = {
    "RELEASE": LotQualityStatus.RELEASED,
    "REJECT": LotQualityStatus.REJECTED,
}


class ResolveTemperatureExcursionUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, excursion_id: str,
                resolution: Literal["RELEASE", "REJECT"], operation_id: str,
                actor_user_id: str, resolution_note: str = "",
                context: InventoryExecutionContext | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.TEMPERATURE_RESOLVE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        with InventoryUnitOfWork(connection) as uow:
            excursion = uow.cold_chain.get_excursion(excursion_id)
        if excursion is None:
            return InventoryResult.fail("Excursión no encontrada", "EXCURSION_NOT_FOUND",
                                        operation_id=operation_id)
        if excursion.resolved:
            return InventoryResult.ok("La excursión ya estaba resuelta",
                                      entity_id=excursion.id, operation_id=operation_id,
                                      already_processed=True)
        if context is not None:
            try:
                context.enforce_warehouse(excursion.warehouse_id)
            except WarehouseScopeError as exc:
                return InventoryResult.fail(str(exc), "SCOPE_DENIED",
                                            operation_id=operation_id)
        if excursion.lot_id:
            lot_result = self._resolve_lot(
                connection, lot_id=excursion.lot_id, resolution=resolution,
                resolution_note=resolution_note, operation_id=f"{operation_id}:lot",
                actor_user_id=actor_user_id, context=context)
            if lot_result is not None and not lot_result.success:
                return lot_result
        try:
            with InventoryUnitOfWork(connection) as uow:
                excursion.resolve(user_id=actor_user_id, note=resolution_note)
                uow.cold_chain.update_resolution(excursion)
                uow.audit.record(entity_type="TEMPERATURE_EXCURSION",
                                 entity_id=excursion.id, action="RESOLVED",
                                 user_id=actor_user_id, operation_id=operation_id,
                                 reason=resolution_note, warehouse_id=excursion.warehouse_id,
                                 lot_id=excursion.lot_id)
                self._emit(uow, operation_id=operation_id, excursion=excursion,
                          actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok("Excursión resuelta", entity_id=excursion.id,
                                  operation_id=operation_id)

    def _resolve_lot(self, connection, *, lot_id, resolution, resolution_note,
                     operation_id, actor_user_id, context):
        with InventoryUnitOfWork(connection) as uow:
            lot = uow.lots.get(lot_id)
        if lot is None or lot.quality_status is not LotQualityStatus.QUARANTINED:
            # Nada que liberar/rechazar — ya fue resuelto por otra vía o el lote
            # no llegó a bloquearse (excursión de sólo alerta, sin auto-bloqueo).
            return None
        new_status = _RESOLUTION_STATUS[resolution]
        return SetLotQualityStatusUseCase(self._auth).execute(
            connection, lot_id=lot_id, new_status=new_status, operation_id=operation_id,
            actor_user_id=actor_user_id, reason=resolution_note, context=context)

    def _emit(self, uow, *, operation_id, excursion, actor_user_id) -> None:
        event_name = InventoryEvents.INVENTORY_TEMPERATURE_EXCURSION_RESOLVED
        payload = build_event_payload(
            event_name, operation_id=operation_id, entity_id=excursion.id,
            lot_id=excursion.lot_id, warehouse_id=excursion.warehouse_id,
            user_id=actor_user_id)
        uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                           payload_json=json.dumps(payload), operation_id=operation_id)
