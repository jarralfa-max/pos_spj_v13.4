"""Output use cases (PROC-10 Outputs, PROC-11 Despiece, PROC-12 Derivados —
§22/§23/§24/§39).

Per §1 (Principio Rector) despiece and derivados share the same núcleo
productivo instead of parallel mechanisms: both are "known input → several
classified outputs + yield check", just with a different `ProcessType`
(CUTTING/DISASSEMBLY/DEBONING/TRIMMING for despiece; GRINDING/MIXING/
MARINATION/FORMULATION for derivados). `RecordProcessOutputsUseCase` is that
one shared orchestration — huesos/grasa/recortes (§23) and molido/mezclado/
marinado/formulación (§24) are just output lines with a descriptive
`product_id` and the right `OutputType`, not special cases.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.ports import InventoryReceiptPort, NullInventoryReceiptPort
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import BLOCKED_QUALITY_STATUSES
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.application.meat_processing.use_cases._shared import (
    summarize_outputs_by_type as _summarize_outputs_by_type,
)
from backend.domain.meat_processing.entities.material_consumption import MaterialConsumption
from backend.domain.meat_processing.entities.process_genealogy_link import ProcessGenealogyLink
from backend.domain.meat_processing.entities.process_output import ProcessOutput
from backend.domain.meat_processing.entities.yield_reconciliation import YieldReconciliation
from backend.domain.meat_processing.enums import OutputType
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingPermissionDeniedError,
)
from backend.domain.meat_processing.policies.yield_reconciliation_policy import (
    YieldReconciliationPolicy,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid

_BLOCKED_QUALITY = BLOCKED_QUALITY_STATUSES

_PERMISSION_BY_OUTPUT_TYPE = {
    OutputType.MAIN_PRODUCT: MeatProcessingPermissions.OUTPUT_CAPTURE,
    OutputType.CO_PRODUCT: MeatProcessingPermissions.CO_PRODUCT_CAPTURE,
    OutputType.BY_PRODUCT: MeatProcessingPermissions.BY_PRODUCT_CAPTURE,
    OutputType.SEMI_FINISHED: MeatProcessingPermissions.SUBPRODUCT_CAPTURE,
    OutputType.WORK_IN_PROGRESS: MeatProcessingPermissions.SUBPRODUCT_CAPTURE,
    OutputType.REWORKABLE: MeatProcessingPermissions.SUBPRODUCT_CAPTURE,
    OutputType.WASTE: MeatProcessingPermissions.WASTE_CAPTURE,
    OutputType.LOSS: MeatProcessingPermissions.WASTE_CAPTURE,
}

_EVENT_BY_OUTPUT_TYPE = {
    OutputType.MAIN_PRODUCT: MeatProcessingEvents.PROCESSING_OUTPUT_PRODUCED,
    OutputType.CO_PRODUCT: MeatProcessingEvents.PROCESSING_CO_PRODUCT_PRODUCED,
    OutputType.BY_PRODUCT: MeatProcessingEvents.PROCESSING_BY_PRODUCT_PRODUCED,
    OutputType.SEMI_FINISHED: MeatProcessingEvents.PROCESSING_SUBPRODUCT_PRODUCED,
    OutputType.WORK_IN_PROGRESS: MeatProcessingEvents.PROCESSING_SUBPRODUCT_PRODUCED,
    OutputType.REWORKABLE: MeatProcessingEvents.PROCESSING_SUBPRODUCT_PRODUCED,
    OutputType.WASTE: MeatProcessingEvents.PROCESSING_WASTE_RECORDED,
    OutputType.LOSS: MeatProcessingEvents.PROCESSING_WASTE_RECORDED,
}


def _capture_output(uow, *, order, operation_id: str, product_id: str, output_type: OutputType,
                     quantity: Decimal, weight: Decimal, actor_user_id: str,
                     processing_batch_id: str | None = None, lot_id: str | None = None,
                     location_id: str | None = None, pieces: int | None = None,
                     unit: str = "unit") -> ProcessOutput:
    output = ProcessOutput(
        id=new_uuid(), operation_id=operation_id, processing_order_id=order.id,
        product_id=product_id, warehouse_id=order.warehouse_id,
        captured_by_user_id=actor_user_id, output_type=output_type,
        processing_batch_id=processing_batch_id, lot_id=lot_id, location_id=location_id,
        quantity=quantity, weight=weight, pieces=pieces, unit=unit)
    uow.outputs.save(output)
    event_name = _EVENT_BY_OUTPUT_TYPE[output_type]
    payload = build_meat_processing_event(
        event_name, operation_id=operation_id, entity_id=output.id, branch_id=order.branch_id,
        warehouse_id=order.warehouse_id, user_id=actor_user_id, output_type=output_type.value,
        quantity=output.quantity, weight=output.weight)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                        payload_json=json.dumps(payload), operation_id=operation_id)
    return output


class CaptureProcessOutputUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, product_id: str,
        output_type: OutputType, quantity, weight, actor_user_id: str,
        processing_batch_id: str | None = None, lot_id: str | None = None,
        location_id: str | None = None, pieces: int | None = None, unit: str = "unit",
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, _PERMISSION_BY_OUTPUT_TYPE[output_type])
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
                output = _capture_output(
                    uow, order=order, operation_id=operation_id, product_id=product_id,
                    output_type=output_type, quantity=quantity, weight=weight,
                    actor_user_id=actor_user_id, processing_batch_id=processing_batch_id,
                    lot_id=lot_id, location_id=location_id, pieces=pieces, unit=unit)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Output capturado", entity_id=output.id, operation_id=operation_id)


class PostProcessOutputUseCase:
    """§39: solicita a Inventario que reciba el output; nunca lo postea
    directamente. §22: un output bloqueado por calidad no puede ingresar a
    stock (PENDING_INSPECTION sí puede — Calidad todavía no existe como
    módulo, PROC-16; solo los estados explícitamente negativos bloquean)."""

    def __init__(
        self,
        authorization: MeatProcessingAuthorizationPolicy | None = None,
        inventory_port: InventoryReceiptPort | None = None,
    ) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()
        self._inventory = inventory_port or NullInventoryReceiptPort()

    def execute(
        self, connection, *, output_id: str, operation_id: str, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.OUTPUT_CAPTURE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                output = uow.outputs.get(output_id)
                if output is None:
                    return MeatProcessingResult.fail(
                        "Output no encontrado", "OUTPUT_NOT_FOUND", operation_id=operation_id)
                order = uow.orders.get(output.processing_order_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if output.inventory_operation_id is not None:
                    return MeatProcessingResult.ok(
                        "Output ya posteado (idempotente)", entity_id=output.id,
                        operation_id=operation_id, already_processed=True)
                if output.quality_status in _BLOCKED_QUALITY:
                    return MeatProcessingResult.fail(
                        "El output está bloqueado por calidad", "OUTPUT_QUALITY_BLOCKED",
                        operation_id=operation_id)
                inventory_operation_id = self._inventory.post_output(
                    operation_id=operation_id, product_id=output.product_id,
                    warehouse_id=output.warehouse_id, quantity=output.quantity,
                    weight=output.weight, lot_id=output.lot_id, location_id=output.location_id)
                if inventory_operation_id is None:
                    return MeatProcessingResult.fail(
                        "Inventario aún no confirma la recepción",
                        "INVENTORY_INTEGRATION_PENDING", operation_id=operation_id)
                output.assign_inventory_operation(inventory_operation_id=inventory_operation_id)
                uow.outputs.save(output)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Output posteado a inventario", entity_id=output.id, operation_id=operation_id)


class RecordProcessOutputsUseCase:
    """§11/§23/§24: one input weight/quantity → many classified outputs +
    yield reconciliation, in a single transaction. This is "despiece" and
    "derivados" both — the difference is only the order's `ProcessType` and
    what the caller labels each output line, not the mechanism.

    `expected_output_quantity`/`expected_output_weight` are **not** the same
    as `input_quantity`/`input_weight` — expected output is normally less
    than input (that ratio *is* the expected yield rate, e.g. a recipe's
    yield profile from PROC-6's snapshot) and must always be supplied by the
    caller, never assumed equal to input (§26 "no hardcodear")."""

    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, actor_user_id: str,
        input_quantity, input_weight, expected_output_quantity, expected_output_weight,
        outputs: list[dict], warning_pct: Decimal, tolerance_pct: Decimal,
        critical_pct: Decimal, processing_batch_id: str | None = None,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            for line in outputs:
                self._auth.require(
                    actor_user_id, _PERMISSION_BY_OUTPUT_TYPE[line["output_type"]])
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                # This call spans several entities, each needing its own valid
                # UUIDv7 operation_id — idempotency is tracked at the whole-call
                # level instead, via the processed-events registry.
                if uow.processed_events.was_processed(operation_id):
                    return MeatProcessingResult.ok(
                        "Ya procesado (idempotente)", operation_id=operation_id,
                        already_processed=True)
                order = uow.orders.get(order_id)
                if order is None:
                    return MeatProcessingResult.fail(
                        "Orden no encontrada", "ORDER_NOT_FOUND", operation_id=operation_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if not outputs:
                    return MeatProcessingResult.fail(
                        "Se requiere al menos un output", "NO_OUTPUTS",
                        operation_id=operation_id)
                captured_ids = []
                captured_outputs = []
                for line in outputs:
                    output = _capture_output(
                        uow, order=order, operation_id=new_uuid(),
                        product_id=line["product_id"], output_type=line["output_type"],
                        quantity=line.get("quantity", Decimal("0")),
                        weight=line.get("weight", Decimal("0")), actor_user_id=actor_user_id,
                        processing_batch_id=processing_batch_id, lot_id=line.get("lot_id"),
                        location_id=line.get("location_id"), pieces=line.get("pieces"),
                        unit=line.get("unit", "unit"))
                    captured_ids.append(output.id)
                    captured_outputs.append(output)
                totals = _summarize_outputs_by_type(captured_outputs)

                reconciliation = YieldReconciliation(
                    id=new_uuid(), operation_id=new_uuid(),
                    processing_order_id=order_id, processing_batch_id=processing_batch_id,
                    input_quantity=input_quantity, input_weight=input_weight,
                    expected_output_quantity=expected_output_quantity,
                    expected_output_weight=expected_output_weight,
                    actual_output_quantity=totals["actual_quantity"],
                    actual_output_weight=totals["actual_weight"],
                    co_product_weight=totals["co_product_weight"],
                    by_product_weight=totals["by_product_weight"],
                    waste_weight=totals["waste_weight"], tolerance_pct=tolerance_pct)
                status = YieldReconciliationPolicy.classify(
                    reconciliation.variance_pct, warning_pct=warning_pct,
                    tolerance_pct=tolerance_pct, critical_pct=critical_pct)
                reconciliation.apply_classification(status)
                uow.yield_reconciliations.save(reconciliation)
                yield_event_id = new_uuid()
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_YIELD_CALCULATED,
                    operation_id=yield_event_id, entity_id=reconciliation.id,
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    user_id=actor_user_id, status=status.value)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_YIELD_CALCULATED,
                    payload_json=json.dumps(payload), operation_id=yield_event_id)
                if status.value in ("OUT_OF_TOLERANCE", "CRITICAL"):
                    alert_operation_id = new_uuid()
                    alert_payload = build_meat_processing_event(
                        MeatProcessingEvents.PROCESSING_YIELD_OUT_OF_TOLERANCE,
                        operation_id=alert_operation_id, entity_id=reconciliation.id,
                        branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                        user_id=actor_user_id, status=status.value)
                    uow.outbox.enqueue(
                        event_id=alert_payload["event_id"],
                        event_name=MeatProcessingEvents.PROCESSING_YIELD_OUT_OF_TOLERANCE,
                        payload_json=json.dumps(alert_payload),
                        operation_id=alert_operation_id)
                uow.processed_events.mark_processed(
                    operation_id, "PROCESSING_OUTPUTS_RECORDED", operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Outputs registrados y rendimiento calculado", entity_id=reconciliation.id,
            operation_id=operation_id, output_ids=captured_ids,
            yield_status=reconciliation.status.value)


class ChainOutputAsConsumptionUseCase:
    """§24 "BOM multinivel / productos intermedios": the output of one order
    becomes the material consumption of another. No new entity — this just
    creates the downstream MaterialConsumption from the upstream ProcessOutput's
    own product/lot/quantity/weight, making the chain explicit and auditable.

    §38 (PROC-18): also records a ProcessGenealogyLink for this same edge, so
    the chain is queryable (trace_upstream/trace_downstream/recall) without
    having to reverse-engineer it from MaterialConsumption rows."""

    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, upstream_output_id: str, downstream_order_id: str,
        operation_id: str, actor_user_id: str,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.CONSUMPTION_CAPTURE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                upstream = uow.outputs.get(upstream_output_id)
                if upstream is None:
                    return MeatProcessingResult.fail(
                        "Output de origen no encontrado", "OUTPUT_NOT_FOUND",
                        operation_id=operation_id)
                downstream_order = uow.orders.get(downstream_order_id)
                if downstream_order is None:
                    return MeatProcessingResult.fail(
                        "Orden destino no encontrada", "ORDER_NOT_FOUND",
                        operation_id=operation_id)
                denied = _scope_fail(
                    context, downstream_order.branch_id, downstream_order.warehouse_id,
                    operation_id)
                if denied is not None:
                    return denied
                if upstream.quality_status in _BLOCKED_QUALITY:
                    return MeatProcessingResult.fail(
                        "El output de origen está bloqueado por calidad",
                        "OUTPUT_QUALITY_BLOCKED", operation_id=operation_id)
                consumption = MaterialConsumption(
                    id=new_uuid(), operation_id=operation_id,
                    processing_order_id=downstream_order_id, product_id=upstream.product_id,
                    warehouse_id=downstream_order.warehouse_id,
                    captured_by_user_id=actor_user_id, lot_id=upstream.lot_id,
                    planned_quantity=upstream.quantity, planned_weight=upstream.weight,
                    unit=upstream.unit)
                consumption.record_actuals(
                    actual_quantity=upstream.quantity, actual_weight=upstream.weight)
                uow.consumptions.save(consumption)
                link = ProcessGenealogyLink(
                    id=new_uuid(), operation_id=operation_id,
                    upstream_entity_type="ProcessOutput", upstream_entity_id=upstream.id,
                    downstream_entity_type="MaterialConsumption",
                    downstream_entity_id=consumption.id, product_id=upstream.product_id,
                    linked_by_user_id=actor_user_id, lot_id=upstream.lot_id,
                    quantity=upstream.quantity, weight=upstream.weight)
                uow.genealogy_links.save(link)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Output encadenado como consumo", entity_id=consumption.id,
            operation_id=operation_id)
