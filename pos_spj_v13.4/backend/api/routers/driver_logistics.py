"""Driver PWA API (master prompt §1 "API", ORD-25) — replaces the legacy
hand-rolled `integrations/delivery_pwa/pwa_server.py` prototype (http.server,
inline-string HTML, in-memory `_TOKENS`) with a real router on the same
FastAPI app procurement's mobile logistics feature already established
(`backend/api/main.py`), reusing the SAME signed `MobileSessionTokenService`
session (`POST /api/mobile/session`, shared with every mobile router — a
driver logging in is not a special case).

Controllers here do no domain logic themselves — every mutation delegates to
`OrdersDeliveryDriverWorkflow`, itself a thin orchestration layer over the
REAL, already-built Orders/Delivery use cases (ORD-15..20). `Idempotency-Key`
(no `If-Match` — this bounded context's aggregates carry no optimistic-
concurrency version field) plus each command's own `clientOperationId` are
what make a retried mobile request safe, same idempotency-by-operation_id
discipline every other Orders/Delivery caller already relies on.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.mobile_session import MobileIdentity, command_payload, idempotency_key_header, mobile_identity
from backend.api.schemas.driver_logistics import (
    AcceptAssignmentRequest, ArriveRequest, DepartRequest, DispatchRequest, RecordAttemptRequest,
    RecordCashCollectionRequest, RejectAssignmentRequest,
)
from backend.application.orders_delivery.integrations.driver_pwa_workflow import (
    DriverPwaOperationError,
)

router = APIRouter(tags=["driver-logistics"])

_ERROR_STATUS = {
    "PERMISSION_DENIED": status.HTTP_403_FORBIDDEN,
    "SEGREGATION_OF_DUTIES": status.HTTP_403_FORBIDDEN,
    "DELIVERY_JOB_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "ASSIGNMENT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "CASH_COLLECTION_NOT_FOUND": status.HTTP_404_NOT_FOUND,
}


class DriverPwaWorkflow(Protocol):
    def list_jobs(self, identity: MobileIdentity) -> dict: ...
    def list_pending_assignments(self, identity: MobileIdentity) -> dict: ...
    def accept_assignment(self, identity: MobileIdentity, assignment_id: str,
                          operation_id: str) -> dict: ...
    def reject_assignment(self, identity: MobileIdentity, assignment_id: str,
                          operation_id: str) -> dict: ...
    def dispatch(self, identity: MobileIdentity, delivery_job_id: str, operation_id: str) -> dict: ...
    def depart(self, identity: MobileIdentity, delivery_job_id: str, operation_id: str) -> dict: ...
    def arrive(self, identity: MobileIdentity, delivery_job_id: str, operation_id: str) -> dict: ...
    def record_attempt(self, identity: MobileIdentity, delivery_job_id: str, operation_id: str,
                       **evidence) -> dict: ...
    def record_cash_collection(self, identity: MobileIdentity, collection_id: str,
                               operation_id: str, **amounts) -> dict: ...


def workflow(request: Request) -> DriverPwaWorkflow:
    value = getattr(request.app.state, "driver_pwa_workflow", None)
    if value is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Workflow de repartidor no configurado")
    return value


def _call(fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except DriverPwaOperationError as exc:
        raise HTTPException(_ERROR_STATUS.get(exc.error_code, status.HTTP_409_CONFLICT),
                            {"code": exc.error_code, "message": exc.message}) from exc


@router.get("/delivery/mobile/jobs")
def list_jobs(user: MobileIdentity = Depends(mobile_identity),
             service: DriverPwaWorkflow = Depends(workflow)) -> dict:
    return _call(service.list_jobs, user)


@router.get("/delivery/mobile/assignments/pending")
def list_pending_assignments(user: MobileIdentity = Depends(mobile_identity),
                             service: DriverPwaWorkflow = Depends(workflow)) -> dict:
    return _call(service.list_pending_assignments, user)


@router.post("/delivery/mobile/assignments/{assignment_id}/accept")
def accept_assignment(assignment_id: str, command: AcceptAssignmentRequest,
                      operation_id: str = Depends(idempotency_key_header),
                      user: MobileIdentity = Depends(mobile_identity),
                      service: DriverPwaWorkflow = Depends(workflow)) -> dict:
    command_payload(command, user, operation_id)
    return _call(service.accept_assignment, user, assignment_id, operation_id)


@router.post("/delivery/mobile/assignments/{assignment_id}/reject")
def reject_assignment(assignment_id: str, command: RejectAssignmentRequest,
                      operation_id: str = Depends(idempotency_key_header),
                      user: MobileIdentity = Depends(mobile_identity),
                      service: DriverPwaWorkflow = Depends(workflow)) -> dict:
    command_payload(command, user, operation_id)
    return _call(service.reject_assignment, user, assignment_id, operation_id)


@router.post("/delivery/mobile/jobs/{delivery_job_id}/dispatch")
def dispatch(delivery_job_id: str, command: DispatchRequest,
            operation_id: str = Depends(idempotency_key_header),
            user: MobileIdentity = Depends(mobile_identity),
            service: DriverPwaWorkflow = Depends(workflow)) -> dict:
    command_payload(command, user, operation_id)
    return _call(service.dispatch, user, delivery_job_id, operation_id)


@router.post("/delivery/mobile/jobs/{delivery_job_id}/depart")
def depart(delivery_job_id: str, command: DepartRequest,
          operation_id: str = Depends(idempotency_key_header),
          user: MobileIdentity = Depends(mobile_identity),
          service: DriverPwaWorkflow = Depends(workflow)) -> dict:
    command_payload(command, user, operation_id)
    return _call(service.depart, user, delivery_job_id, operation_id)


@router.post("/delivery/mobile/jobs/{delivery_job_id}/arrive")
def arrive(delivery_job_id: str, command: ArriveRequest,
          operation_id: str = Depends(idempotency_key_header),
          user: MobileIdentity = Depends(mobile_identity),
          service: DriverPwaWorkflow = Depends(workflow)) -> dict:
    command_payload(command, user, operation_id)
    return _call(service.arrive, user, delivery_job_id, operation_id)


@router.post("/delivery/mobile/jobs/{delivery_job_id}/attempts")
def record_attempt(delivery_job_id: str, command: RecordAttemptRequest,
                   operation_id: str = Depends(idempotency_key_header),
                   user: MobileIdentity = Depends(mobile_identity),
                   service: DriverPwaWorkflow = Depends(workflow)) -> dict:
    command_payload(command, user, operation_id)
    return _call(
        service.record_attempt, user, delivery_job_id, operation_id,
        successful=command.successful, recipient_name=command.recipientName,
        signature_reference=command.signatureReference, photo_reference=command.photoReference,
        pin_verified=command.pinVerified, latitude=command.latitude, longitude=command.longitude,
        notes=command.notes, failure_reason=command.failureReason)


@router.post("/delivery/mobile/cash-collections/{collection_id}/record")
def record_cash_collection(collection_id: str, command: RecordCashCollectionRequest,
                           operation_id: str = Depends(idempotency_key_header),
                           user: MobileIdentity = Depends(mobile_identity),
                           service: DriverPwaWorkflow = Depends(workflow)) -> dict:
    command_payload(command, user, operation_id)
    return _call(
        service.record_cash_collection, user, collection_id, operation_id,
        collected_amount=Decimal(command.collectedAmount), reference=command.reference)
