"""OrdersDeliveryDriverWorkflow — the REAL implementation the driver PWA
router (`backend/api/routers/driver_logistics.py`, ORD-25 §1 "API") calls
into. Mirrors the shape `backend/api/routers/mobile_logistics.py`'s own
`OriginPurchaseWorkflow` Protocol expects (methods take the caller's
`MobileIdentity` first, return JSON-ready dicts) — no concrete
implementation of THAT protocol exists anywhere in the repo yet either, so
this is the first one for any mobile router, not just for Pedidos/Delivery.

Never touches SQL directly — every mutation goes through the SAME
`OrdersDeliveryUnitOfWork`-backed use cases the desktop ERP already uses
(`AcceptAssignmentUseCase`/`DispatchDeliveryJobUseCase`/etc, ORD-15..20).
The driver's own granted permissions travel inside their signed
`MobileIdentity.permissions` tuple (set at login time from the SAME RBAC
`usuarios_roles`/`roles` tables the desktop app reads) — `_IdentityPermission
Checker` adapts that tuple into the `PermissionChecker` protocol every
Orders/Delivery use case already expects, so this workflow re-validates
permissions exactly like the desktop UI does, never trusting the PWA client.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.api.mobile_session import MobileIdentity
from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.result import OrderResult
from backend.application.orders_delivery.use_cases.cash_collection_use_cases import (
    RecordCashCollectionUseCase,
)
from backend.application.orders_delivery.use_cases.dispatch_use_cases import (
    ConfirmArrivalUseCase,
    DispatchDeliveryJobUseCase,
    MarkInTransitUseCase,
    RecordDeliveryAttemptUseCase,
)
from backend.application.orders_delivery.use_cases.driver_use_cases import (
    AcceptAssignmentUseCase,
    RejectAssignmentUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.address_repository import (
    OrderAddressRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_job_repository import (
    DeliveryJobRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.driver_repository import (
    DeliveryAssignmentRepository,
)


class DriverPwaOperationError(Exception):
    """Raised when an underlying use case fails — carries the SAME
    `error_code`/`message` shape `OrderResult.fail()` already produces so
    the API router (`backend/api/routers/driver_logistics.py`) can map it to
    an HTTP status without this application-layer module importing FastAPI
    itself (§ layering: application must not depend on a web framework)."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class _IdentityPermissionChecker:
    def __init__(self, identity: MobileIdentity) -> None:
        self._permissions = set(identity.permissions)

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return permission_code in self._permissions


def _auth_for(identity: MobileIdentity) -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy(_IdentityPermissionChecker(identity))


def _raise_for(result: OrderResult) -> None:
    if not result.success:
        raise DriverPwaOperationError(result.error_code or "VALIDATION", result.message)


def _job_view(connection, job) -> dict:
    order = CustomerOrderRepository(connection).get(job.order_id)
    address = OrderAddressRepository(connection).get_by_order_id(job.order_id)
    return {
        "deliveryJobId": job.id,
        "orderId": job.order_id,
        "deliveryNumber": job.delivery_number,
        "status": job.status.value,
        "assignedDriverId": job.assigned_driver_id,
        "deliveryFee": str(job.delivery_fee),
        "cashToCollect": str(job.cash_to_collect),
        "paymentMethodExpected": job.payment_method_expected,
        "orderNumber": order.order_number if order else None,
        "contactName": order.contact_name if order else None,
        "contactPhone": order.contact_phone if order else None,
        "address": None if address is None else {
            "street": address.street, "exteriorNumber": address.exterior_number,
            "interiorNumber": address.interior_number, "neighborhood": address.neighborhood,
            "municipality": address.municipality, "state": address.state,
            "references": address.references, "latitude": address.latitude,
            "longitude": address.longitude,
        },
    }


def _assignment_view(assignment) -> dict:
    return {
        "assignmentId": assignment.id, "deliveryJobId": assignment.delivery_job_id,
        "status": assignment.status.value, "assignedAt": assignment.assigned_at,
    }


@dataclass(slots=True)
class OrdersDeliveryDriverWorkflow:
    connection_factory: object  # Callable[[], sqlite3.Connection]

    def _conn(self):
        return self.connection_factory()

    def list_jobs(self, identity: MobileIdentity) -> dict:
        conn = self._conn()
        jobs = DeliveryJobRepository(conn).list_for_driver(identity.user_id)
        return {"jobs": [_job_view(conn, job) for job in jobs]}

    def list_pending_assignments(self, identity: MobileIdentity) -> dict:
        conn = self._conn()
        assignments = DeliveryAssignmentRepository(conn).list_pending_for_driver(identity.user_id)
        return {"assignments": [_assignment_view(a) for a in assignments]}

    def accept_assignment(self, identity: MobileIdentity, assignment_id: str,
                           operation_id: str) -> dict:
        conn = self._conn()
        result = AcceptAssignmentUseCase(_auth_for(identity)).execute(
            conn, assignment_id=assignment_id, actor_user_id=identity.user_id,
            operation_id=operation_id)
        _raise_for(result)
        return {"assignmentId": assignment_id, "status": "ACCEPTED"}

    def reject_assignment(self, identity: MobileIdentity, assignment_id: str,
                           operation_id: str) -> dict:
        conn = self._conn()
        result = RejectAssignmentUseCase(_auth_for(identity)).execute(
            conn, assignment_id=assignment_id, actor_user_id=identity.user_id,
            operation_id=operation_id)
        _raise_for(result)
        return {"assignmentId": assignment_id, "status": "REJECTED"}

    def dispatch(self, identity: MobileIdentity, delivery_job_id: str, operation_id: str) -> dict:
        conn = self._conn()
        result = DispatchDeliveryJobUseCase(_auth_for(identity)).execute(
            conn, delivery_job_id=delivery_job_id, actor_user_id=identity.user_id,
            operation_id=operation_id)
        _raise_for(result)
        return {"deliveryJobId": delivery_job_id, "status": "DISPATCHED"}

    def depart(self, identity: MobileIdentity, delivery_job_id: str, operation_id: str) -> dict:
        conn = self._conn()
        result = MarkInTransitUseCase(_auth_for(identity)).execute(
            conn, delivery_job_id=delivery_job_id, actor_user_id=identity.user_id,
            operation_id=operation_id)
        _raise_for(result)
        return {"deliveryJobId": delivery_job_id, "status": "IN_TRANSIT"}

    def arrive(self, identity: MobileIdentity, delivery_job_id: str, operation_id: str) -> dict:
        conn = self._conn()
        result = ConfirmArrivalUseCase(_auth_for(identity)).execute(
            conn, delivery_job_id=delivery_job_id, actor_user_id=identity.user_id,
            operation_id=operation_id)
        _raise_for(result)
        return {"deliveryJobId": delivery_job_id, "status": "ARRIVED"}

    def record_attempt(
        self, identity: MobileIdentity, delivery_job_id: str, operation_id: str, *,
        successful: bool, recipient_name: str | None, signature_reference: str | None,
        photo_reference: str | None, pin_verified: bool, latitude: float | None,
        longitude: float | None, notes: str | None, failure_reason: str | None,
    ) -> dict:
        conn = self._conn()
        result = RecordDeliveryAttemptUseCase(_auth_for(identity)).execute(
            conn, delivery_job_id=delivery_job_id, successful=successful,
            actor_user_id=identity.user_id, operation_id=operation_id,
            recipient_name=recipient_name, signature_reference=signature_reference,
            photo_reference=photo_reference, pin_verified=pin_verified, latitude=latitude,
            longitude=longitude, notes=notes, failure_reason=failure_reason)
        _raise_for(result)
        return {"deliveryJobId": delivery_job_id, "successful": successful}

    def record_cash_collection(
        self, identity: MobileIdentity, collection_id: str, operation_id: str, *,
        collected_amount: Decimal, reference: str | None,
    ) -> dict:
        conn = self._conn()
        result = RecordCashCollectionUseCase(_auth_for(identity)).execute(
            conn, collection_id=collection_id, collected_amount=collected_amount,
            actor_user_id=identity.user_id, operation_id=operation_id, reference=reference)
        _raise_for(result)
        return {"collectionId": collection_id}
