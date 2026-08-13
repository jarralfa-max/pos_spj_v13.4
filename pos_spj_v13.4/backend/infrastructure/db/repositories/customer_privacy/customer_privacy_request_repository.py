"""CustomerPrivacyRequestRepository — persists the CustomerPrivacyRequest
aggregate. Mirrors
backend/infrastructure/db/repositories/customer_service/service_case_repository.py.
"""

from __future__ import annotations

from backend.domain.customer_privacy.entities.customer_privacy_request import (
    CustomerPrivacyRequest,
)
from backend.domain.customer_privacy.enums import PrivacyRequestStatus, PrivacyRequestType
from backend.domain.customer_privacy.value_objects.privacy_request_code import (
    PrivacyRequestCode,
)
from backend.infrastructure.db.repositories.customer_privacy.base import (
    CustomerPrivacyRepositoryBase,
)

_REQUEST_COLS = (
    "id, request_number, customer_id, request_type, description, status,"
    " related_consent_id, logged_by_user_id, validated_by_user_id,"
    " processed_by_user_id, resolution_notes, received_at, validated_at,"
    " started_at, completed_at, rejected_at, cancelled_at, operation_id,"
    " created_at, updated_at"
)


class CustomerPrivacyRequestRepository(CustomerPrivacyRepositoryBase):
    def next_code(self) -> PrivacyRequestCode:
        last = self._scalar(
            "SELECT request_number FROM customer_privacy_requests"
            " ORDER BY CAST(SUBSTR(request_number, 6) AS INTEGER) DESC LIMIT 1")
        seq = (int(last.split("-")[1]) + 1) if last else 1
        return PrivacyRequestCode.from_sequence(seq)

    def save(self, request: CustomerPrivacyRequest, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customer_privacy_requests ({_REQUEST_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(request, operation_id or request.operation_id))

    def update(self, request: CustomerPrivacyRequest) -> None:
        self._execute(
            "UPDATE customer_privacy_requests SET status=?, validated_by_user_id=?,"
            " processed_by_user_id=?, resolution_notes=?, validated_at=?, started_at=?,"
            " completed_at=?, rejected_at=?, cancelled_at=?, updated_at=? WHERE id=?",
            (request.status.value, request.validated_by_user_id, request.processed_by_user_id,
             request.resolution_notes, request.validated_at, request.started_at,
             request.completed_at, request.rejected_at, request.cancelled_at,
             request.updated_at, request.id))

    def get(self, request_id: str) -> CustomerPrivacyRequest | None:
        row = self._query_one(
            f"SELECT {_REQUEST_COLS} FROM customer_privacy_requests WHERE id=?", (request_id,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> CustomerPrivacyRequest | None:
        row = self._query_one(
            f"SELECT {_REQUEST_COLS} FROM customer_privacy_requests WHERE operation_id=?",
            (operation_id,))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[CustomerPrivacyRequest]:
        rows = self._query(
            f"SELECT {_REQUEST_COLS} FROM customer_privacy_requests"
            " WHERE customer_id=? ORDER BY received_at DESC", (customer_id,))
        return [self._hydrate(r) for r in rows]

    def list_by_status(self, status: str, *,
                        limit: int = 200, offset: int = 0) -> list[CustomerPrivacyRequest]:
        rows = self._query(
            f"SELECT {_REQUEST_COLS} FROM customer_privacy_requests WHERE status=?"
            " ORDER BY received_at ASC LIMIT ? OFFSET ?", (status, limit, offset))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(request: CustomerPrivacyRequest, operation_id: str | None) -> tuple:
        return (
            request.id, str(request.code), request.customer_id, request.request_type.value,
            request.description, request.status.value, request.related_consent_id,
            request.logged_by_user_id, request.validated_by_user_id,
            request.processed_by_user_id, request.resolution_notes, request.received_at,
            request.validated_at, request.started_at, request.completed_at,
            request.rejected_at, request.cancelled_at, operation_id, request.created_at,
            request.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerPrivacyRequest:
        return CustomerPrivacyRequest(
            id=row["id"], code=PrivacyRequestCode(row["request_number"]),
            customer_id=row["customer_id"], request_type=PrivacyRequestType(row["request_type"]),
            description=row["description"] or "", status=PrivacyRequestStatus(row["status"]),
            related_consent_id=row["related_consent_id"],
            logged_by_user_id=row["logged_by_user_id"],
            validated_by_user_id=row["validated_by_user_id"],
            processed_by_user_id=row["processed_by_user_id"],
            resolution_notes=row["resolution_notes"] or "", received_at=row["received_at"],
            validated_at=row["validated_at"], started_at=row["started_at"],
            completed_at=row["completed_at"], rejected_at=row["rejected_at"],
            cancelled_at=row["cancelled_at"], operation_id=row["operation_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
