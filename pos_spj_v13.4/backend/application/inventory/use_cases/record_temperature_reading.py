"""RecordTemperatureReadingUseCase — capture a temperature and act on excursions (§21).

Classifies the reading against the configured cold-chain range; a non-compliant
reading records an excursion and emits INVENTORY_TEMPERATURE_ALERT. When the
product/warehouse is configured to auto-block, an out-of-range reading quarantines
the affected lot (INVENTORY_LOT_BLOCKED) — Inventory keeps the status; Quality
decides release or disposal.
"""

from __future__ import annotations

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.domain.inventory.entities.cold_chain import (
    TemperatureExcursion,
    TemperatureReading,
)
from backend.domain.inventory.enums import (
    ColdChainStatus,
    ExcursionAction,
    LotQualityStatus,
    TemperaturePoint,
)
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.domain.inventory.policies.cold_chain_policy import ColdChainPolicy
from backend.domain.inventory.value_objects.cold_chain import ColdChainRange
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


class RecordTemperatureReadingUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()
        self._policy = ColdChainPolicy()

    def execute(self, connection, *, sensor_id: str, warehouse_id: str, temperature,
                reading_point: TemperaturePoint, min_temp, max_temp, operation_id: str,
                actor_user_id: str, warning_margin=0, unit: str = "C",
                location_id: str | None = None, lot_id: str | None = None,
                auto_block: bool = False) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.TEMPERATURE_RECORD)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        try:
            cold_range = ColdChainRange(min_temp=min_temp, max_temp=max_temp,
                                        warning_margin=warning_margin, unit=unit)
            status = self._policy.classify(temperature, cold_range)
            action = self._policy.decide_action(status, auto_block=auto_block)

            with InventoryUnitOfWork(connection) as uow:
                reading = TemperatureReading.create(
                    sensor_id=sensor_id, warehouse_id=warehouse_id, temperature=temperature,
                    reading_point=reading_point, status=status, unit=unit,
                    location_id=location_id, lot_id=lot_id)
                uow.cold_chain.save_reading(reading)

                if self._policy.is_excursion(status):
                    excursion = TemperatureExcursion.create(
                        reading_id=reading.id, warehouse_id=warehouse_id, status=status,
                        temperature=temperature, min_temp=cold_range.min_temp,
                        max_temp=cold_range.max_temp, action_taken=action, lot_id=lot_id)
                    uow.cold_chain.save_excursion(excursion)

                    if action is ExcursionAction.QUARANTINE and lot_id:
                        uow.lots.set_quality_status(lot_id, LotQualityStatus.QUARANTINED)
                        self._emit(uow, InventoryEvents.INVENTORY_LOT_BLOCKED,
                                   operation_id=operation_id, entity_id=lot_id,
                                   lot_id=lot_id, warehouse_id=warehouse_id,
                                   actor_user_id=actor_user_id)
                    self._emit(uow, InventoryEvents.INVENTORY_TEMPERATURE_ALERT,
                               operation_id=operation_id, entity_id=reading.id,
                               lot_id=lot_id, warehouse_id=warehouse_id,
                               actor_user_id=actor_user_id, status=status.value,
                               action=action.value)
                    uow.audit.record(entity_type="TEMPERATURE_EXCURSION",
                                     entity_id=reading.id, action=status.value,
                                     user_id=actor_user_id, operation_id=operation_id,
                                     warehouse_id=warehouse_id, lot_id=lot_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok(f"Lectura registrada ({status.value})",
                                  entity_id=reading.id, operation_id=operation_id,
                                  status=status.value, action=action.value)

    def _emit(self, uow, event_name, *, operation_id, entity_id, warehouse_id,
              actor_user_id, lot_id=None, **extra) -> None:
        payload = build_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id, lot_id=lot_id,
            warehouse_id=warehouse_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                           payload_json=json.dumps(payload), operation_id=operation_id)
