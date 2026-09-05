"""Consumption and weighing use cases (PROC-9, §17/§21/§39).

Weight stability and manual-override structural rules are already enforced by
`ProcessWeighing.__post_init__` (PROC-2) — this layer adds the *authorization*
side of a manual override (§52 hot authorization: the authorizer must hold
`WEIGHT_MANUAL_OVERRIDE` and is recorded in `meat_processing_authorization_log`,
the first real use of that PROC-1/PROC-3 infrastructure). Consumption posting
never writes Inventory directly (§39) — it asks `InventoryConsumptionPort` and
only marks POSTED once Inventory actually confirms a movement id.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.ports import (
    InventoryConsumptionPort,
    NullInventoryConsumptionPort,
)
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.domain.meat_processing.entities.material_consumption import MaterialConsumption
from backend.domain.meat_processing.entities.process_weighing import ProcessWeighing
from backend.domain.meat_processing.enums import ConsumptionStatus, WeighingType
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingInvariantError,
    MeatProcessingPermissionDeniedError,
)
from backend.domain.meat_processing.policies.consumption_policy import ConsumptionPolicy
from backend.domain.meat_processing.value_objects.authorization_grant import AuthorizationGrant
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


class CaptureProcessWeighingUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, weighing_type: WeighingType,
        gross_weight, actor_user_id: str, tare_weight=Decimal("0"), unit: str = "kg",
        processing_batch_id: str | None = None, scale_id: str | None = None,
        stable: bool = True, manual_override: bool = False,
        authorized_by_user_id: str | None = None, override_reason: str = "",
        source_reference: str | None = None,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.WEIGHT_CAPTURE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        if manual_override:
            try:
                self._auth.require(
                    authorized_by_user_id, MeatProcessingPermissions.WEIGHT_MANUAL_OVERRIDE)
            except MeatProcessingPermissionDeniedError as exc:
                return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                order = uow.orders.get(order_id)
                if order is None:
                    return MeatProcessingResult.fail(
                        "Orden no encontrada", "ORDER_NOT_FOUND", operation_id=operation_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                weighing = ProcessWeighing(
                    id=new_uuid(), operation_id=operation_id, processing_order_id=order_id,
                    captured_by_user_id=actor_user_id, weighing_type=weighing_type,
                    gross_weight=gross_weight, tare_weight=tare_weight, unit=unit,
                    processing_batch_id=processing_batch_id, scale_id=scale_id, stable=stable,
                    manual_override=manual_override, authorized_by_user_id=authorized_by_user_id,
                    source_reference=source_reference)
                uow.weighings.save(weighing)
                if manual_override:
                    uow.authorization_log.record(AuthorizationGrant(
                        permission_code=MeatProcessingPermissions.WEIGHT_MANUAL_OVERRIDE,
                        requested_by=actor_user_id, authorized_by=authorized_by_user_id,
                        operation_id=operation_id,
                        reason=override_reason or "Peso capturado manualmente",
                        weight=weighing.net_weight))
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_WEIGHT_CAPTURED, operation_id=operation_id,
                    entity_id=weighing.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id,
                    net_weight=weighing.net_weight)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_WEIGHT_CAPTURED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Pesaje capturado", entity_id=weighing.id, operation_id=operation_id,
            net_weight=str(weighing.net_weight))


class CaptureMaterialConsumptionUseCase:
    """Creates the consumption and records its actuals in one call (the common
    real flow: an operator weighs, then logs the real quantity consumed)."""

    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, product_id: str,
        warehouse_id: str, planned_quantity, planned_weight, actual_quantity, actual_weight,
        actor_user_id: str, processing_batch_id: str | None = None, lot_id: str | None = None,
        location_id: str | None = None, unit: str = "unit", weighing_id: str | None = None,
        tolerance_pct=None, authorized_by_user_id: str | None = None, override_reason: str = "",
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.CONSUMPTION_CAPTURE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                order = uow.orders.get(order_id)
                if order is None:
                    return MeatProcessingResult.fail(
                        "Orden no encontrada", "ORDER_NOT_FOUND", operation_id=operation_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if tolerance_pct is not None:
                    try:
                        ConsumptionPolicy.validate_overage(
                            planned_quantity, actual_quantity, tolerance_pct=tolerance_pct)
                    except MeatProcessingInvariantError as exc:
                        try:
                            self._auth.require(
                                authorized_by_user_id,
                                MeatProcessingPermissions.CONSUMPTION_OVERRIDE)
                        except MeatProcessingPermissionDeniedError:
                            return _fail(exc, operation_id)
                        uow.authorization_log.record(AuthorizationGrant(
                            permission_code=MeatProcessingPermissions.CONSUMPTION_OVERRIDE,
                            requested_by=actor_user_id, authorized_by=authorized_by_user_id,
                            operation_id=operation_id,
                            reason=override_reason or str(exc), quantity=actual_quantity))
                consumption = MaterialConsumption(
                    id=new_uuid(), operation_id=operation_id, processing_order_id=order_id,
                    product_id=product_id, warehouse_id=warehouse_id,
                    captured_by_user_id=actor_user_id, processing_batch_id=processing_batch_id,
                    lot_id=lot_id, location_id=location_id, planned_quantity=planned_quantity,
                    planned_weight=planned_weight, unit=unit, weighing_id=weighing_id)
                consumption.record_actuals(
                    actual_quantity=actual_quantity, actual_weight=actual_weight)
                uow.consumptions.save(consumption)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Consumo capturado", entity_id=consumption.id, operation_id=operation_id,
            status=consumption.status.value)


class PostMaterialConsumptionUseCase:
    """§39: requests the movement from Inventory; never posts it directly."""

    def __init__(
        self,
        authorization: MeatProcessingAuthorizationPolicy | None = None,
        inventory_port: InventoryConsumptionPort | None = None,
    ) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()
        self._inventory = inventory_port or NullInventoryConsumptionPort()

    def execute(
        self, connection, *, consumption_id: str, operation_id: str, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.CONSUMPTION_CAPTURE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                consumption = uow.consumptions.get(consumption_id)
                if consumption is None:
                    return MeatProcessingResult.fail(
                        "Consumo no encontrado", "CONSUMPTION_NOT_FOUND",
                        operation_id=operation_id)
                order = uow.orders.get(consumption.processing_order_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if consumption.status is ConsumptionStatus.POSTED:
                    return MeatProcessingResult.ok(
                        "Consumo ya posteado (idempotente)", entity_id=consumption.id,
                        operation_id=operation_id, already_processed=True)
                inventory_operation_id = self._inventory.post_consumption(
                    operation_id=operation_id, product_id=consumption.product_id,
                    warehouse_id=consumption.warehouse_id, quantity=consumption.actual_quantity,
                    weight=consumption.actual_weight, lot_id=consumption.lot_id,
                    location_id=consumption.location_id)
                if inventory_operation_id is None:
                    return MeatProcessingResult.fail(
                        "Inventario aún no confirma el movimiento",
                        "INVENTORY_INTEGRATION_PENDING", operation_id=operation_id)
                consumption.post(inventory_operation_id=inventory_operation_id)
                uow.consumptions.save(consumption)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_MATERIAL_CONSUMED, operation_id=operation_id,
                    entity_id=consumption.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id,
                    inventory_operation_id=inventory_operation_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_MATERIAL_CONSUMED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Consumo posteado", entity_id=consumption.id, operation_id=operation_id)
