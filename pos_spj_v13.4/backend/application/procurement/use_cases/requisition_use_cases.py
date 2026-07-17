"""Purchase-requisition use cases (§58) — the enterprise entry point.

A need (POS replenishment / forecast / minimum stock / customer order) becomes a
requisition; submission sends it to approval; approval sources it into an order.
Every transition re-validates its granular permission, is atomic, audited, and
publishes its canonical event post-commit. Requester ≠ approver (segregation).
"""

from __future__ import annotations

import json

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.entities import PurchaseRequisition, RequisitionLine
from backend.domain.procurement.enums import PurchaseType, SourceChannel
from backend.domain.procurement.events import ProcurementEvents, build_event_payload
from backend.domain.procurement.exceptions import (
    ProcurementDomainError,
    PurchasePermissionDeniedError,
)
from backend.domain.procurement.policies import SegregationOfDutiesPolicy
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


def _year() -> int:
    from datetime import date
    return date.today().year


def _emit(uow, event_name, *, document_id, operation_id, actor_user_id=None, **extra):
    payload = build_event_payload(event_name, operation_id=operation_id,
                                  document_id=document_id, user_id=actor_user_id, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


class CreatePurchaseRequisitionUseCase:
    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str, branch_id: str,
                purchase_type: str, lines: list[dict], priority: str = "NORMAL",
                business_reason: str = "",
                source_channel: str = SourceChannel.PROCUREMENT_DESKTOP.value,
                source_reference_id: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.REQUISITION_CREATE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            existing = uow.requisitions.get_by_operation(operation_id)
            if existing is not None:
                return ProcurementResult.ok("Solicitud ya registrada", entity_id=existing.id,
                                            operation_id=operation_id,
                                            status=existing.status.value)
            try:
                req = PurchaseRequisition.create(
                    uow.sequences.next_number("SC", _year()), branch_id, actor_user_id,
                    PurchaseType(purchase_type), priority=priority,
                    business_reason=business_reason,
                    source_channel=SourceChannel(source_channel),
                    source_reference_id=source_reference_id)
                for raw in lines:
                    cost = (Money(str(raw["estimated_unit_cost"]))
                            if raw.get("estimated_unit_cost") is not None else None)
                    req.add_line(RequisitionLine.create(
                        raw["product_id"], str(raw["quantity"]), estimated_unit_cost=cost))
                if not req.lines:
                    return ProcurementResult.fail("La solicitud requiere al menos una línea",
                                                  "EMPTY", operation_id=operation_id)
            except (ProcurementDomainError, ValueError) as exc:
                return ProcurementResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.requisitions.save(req)
            uow.requisitions.set_operation_id(req.id, operation_id)
            uow.audit.record(action=ProcurementEvents.PURCHASE_REQUISITION_CREATED,
                             actor_user_id=actor_user_id, document_id=req.id,
                             reason="alta solicitud", operation_id=operation_id,
                             branch_id=branch_id, source_channel=source_channel)
            _emit(uow, ProcurementEvents.PURCHASE_REQUISITION_CREATED, document_id=req.id,
                  operation_id=operation_id, actor_user_id=actor_user_id, branch_id=branch_id,
                  document_number=req.document_number)
        return ProcurementResult.ok("Solicitud creada", entity_id=req.id,
                                    operation_id=operation_id, status=req.status.value,
                                    document_number=req.document_number)


class SubmitPurchaseRequisitionUseCase:
    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, requisition_id: str,
                operation_id: str) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.REQUISITION_SUBMIT)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            req = uow.requisitions.get(requisition_id)
            if req is None:
                return ProcurementResult.fail("Solicitud inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            try:
                req.submit()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            uow.requisitions.save(req)
            uow.audit.record(action=ProcurementEvents.PURCHASE_REQUISITION_SUBMITTED,
                             actor_user_id=actor_user_id, document_id=req.id,
                             operation_id=operation_id, branch_id=req.branch_id)
            _emit(uow, ProcurementEvents.PURCHASE_REQUISITION_SUBMITTED, document_id=req.id,
                  operation_id=operation_id, actor_user_id=actor_user_id)
        return ProcurementResult.ok("Solicitud enviada a aprobación", entity_id=req.id,
                                    operation_id=operation_id, status=req.status.value)


class ApprovePurchaseRequisitionUseCase:
    """Approve or reject. Requester can never approve their own requisition."""

    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._sod = SegregationOfDutiesPolicy()

    def execute(self, connection, *, approver_user_id: str, requisition_id: str,
                operation_id: str, approve: bool = True,
                reason: str = "") -> ProcurementResult:
        permission = (PurchasePermissions.REQUISITION_APPROVE if approve
                      else PurchasePermissions.REQUISITION_REJECT)
        try:
            self._auth.require(approver_user_id, permission)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            req = uow.requisitions.get(requisition_id)
            if req is None:
                return ProcurementResult.fail("Solicitud inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            try:
                self._sod.enforce_distinct(
                    req.requested_by_user_id, approver_user_id,
                    "quien solicita no aprueba su propia solicitud")
                if approve:
                    req.approve(approver_user_id)
                    event = ProcurementEvents.PURCHASE_REQUISITION_APPROVED
                else:
                    req.reject(approver_user_id)
                    event = ProcurementEvents.PURCHASE_REQUISITION_REJECTED
            except ProcurementDomainError as exc:
                code = ("SEGREGATION" if "Separación" in str(exc) else "INVALID_STATE")
                return ProcurementResult.fail(str(exc), code, operation_id=operation_id)
            uow.requisitions.save(req)
            uow.audit.record(action=event, actor_user_id=approver_user_id,
                             authorized_by=approver_user_id, document_id=req.id,
                             reason=reason, operation_id=operation_id, branch_id=req.branch_id)
            _emit(uow, event, document_id=req.id, operation_id=operation_id,
                  actor_user_id=approver_user_id, authorized_by=approver_user_id)
        return ProcurementResult.ok("Solicitud procesada", entity_id=req.id,
                                    operation_id=operation_id, status=req.status.value)
