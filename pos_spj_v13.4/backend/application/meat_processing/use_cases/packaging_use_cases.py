"""Packaging use cases (PROC-13, §25). "La impresión no determina el éxito
productivo" — a packaging execution is complete on its own; printing (and
reprinting) is a separate, non-blocking step tracked against it.
"""

from __future__ import annotations

import json

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.domain.meat_processing.entities.packaging_execution import PackagingExecution
from backend.domain.meat_processing.entities.production_label import ProductionLabel
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingPermissionDeniedError,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


class ExecutePackagingUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, product_id: str,
        packaging_material_id: str, package_quantity: int, net_weight, gross_weight,
        actor_user_id: str, tare_weight=0, lot_id: str | None = None,
        process_output_id: str | None = None, expiration_date=None,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.PACKAGING_EXECUTE)
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
                packaging = PackagingExecution(
                    id=new_uuid(), operation_id=operation_id, processing_order_id=order_id,
                    product_id=product_id, packaging_material_id=packaging_material_id,
                    package_quantity=package_quantity, net_weight=net_weight,
                    gross_weight=gross_weight, tare_weight=tare_weight,
                    packaged_by_user_id=actor_user_id, lot_id=lot_id,
                    process_output_id=process_output_id, expiration_date=expiration_date)
                uow.packaging_executions.save(packaging)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_PACKAGING_EXECUTED,
                    operation_id=operation_id, entity_id=packaging.id,
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    user_id=actor_user_id, package_quantity=packaging.package_quantity,
                    net_weight=packaging.net_weight)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_PACKAGING_EXECUTED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Empaque ejecutado", entity_id=packaging.id, operation_id=operation_id)


class PrintProductionLabelUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, packaging_execution_id: str, operation_id: str,
        label_template_id: str, barcode: str, qr_traceability_reference: str,
        actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.LABEL_PRINT)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                packaging = uow.packaging_executions.get(packaging_execution_id)
                if packaging is None:
                    return MeatProcessingResult.fail(
                        "Empaque no encontrado", "PACKAGING_NOT_FOUND",
                        operation_id=operation_id)
                existing = next(
                    (label for label in uow.production_labels.list_by_packaging(
                        packaging_execution_id) if label.operation_id == operation_id), None)
                if existing is not None:
                    return MeatProcessingResult.ok(
                        "Etiqueta ya impresa (idempotente)", entity_id=existing.id,
                        operation_id=operation_id, already_processed=True)
                label = ProductionLabel(
                    id=new_uuid(), operation_id=operation_id,
                    packaging_execution_id=packaging_execution_id,
                    label_template_id=label_template_id, barcode=barcode,
                    qr_traceability_reference=qr_traceability_reference)
                label.mark_printed(actor_user_id=actor_user_id)
                uow.production_labels.save(label)
                order = uow.orders.get(packaging.processing_order_id)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_LABEL_PRINTED, operation_id=operation_id,
                    entity_id=label.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id,
                    reprint=False)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_LABEL_PRINTED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Etiqueta impresa", entity_id=label.id, operation_id=operation_id)


class ReprintProductionLabelUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, label_id: str, operation_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.LABEL_REPRINT)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                label = uow.production_labels.get(label_id)
                if label is None:
                    return MeatProcessingResult.fail(
                        "Etiqueta no encontrada", "LABEL_NOT_FOUND", operation_id=operation_id)
                packaging = uow.packaging_executions.get(label.packaging_execution_id)
                order = uow.orders.get(packaging.processing_order_id)
                label.mark_printed(actor_user_id=actor_user_id)
                uow.production_labels.save(label)
                payload = build_meat_processing_event(
                    MeatProcessingEvents.PROCESSING_LABEL_PRINTED, operation_id=operation_id,
                    entity_id=label.id, branch_id=order.branch_id,
                    warehouse_id=order.warehouse_id, user_id=actor_user_id, reprint=True,
                    reprint_count=label.reprint_count)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=MeatProcessingEvents.PROCESSING_LABEL_PRINTED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Etiqueta reimpresa", entity_id=label.id, operation_id=operation_id,
            reprint_count=label.reprint_count)
