"""ServiceCaseRepository — persists the CustomerServiceCase aggregate.
Mirrors backend/infrastructure/db/repositories/crm/opportunity_repository.py.
"""

from __future__ import annotations

from backend.domain.customer_service.entities.customer_service_case import CustomerServiceCase
from backend.domain.customer_service.enums import (
    ServiceCaseChannel,
    ServiceCasePriority,
    ServiceCaseStatus,
    ServiceCaseType,
)
from backend.domain.customer_service.value_objects.service_case_code import ServiceCaseCode
from backend.infrastructure.db.repositories.customer_service.base import (
    CustomerServiceRepositoryBase,
)

_CASE_COLS = (
    "id, case_number, customer_id, case_type, subject, status, priority,"
    " category_id, description, assigned_user_id, channel, origin_branch_id,"
    " territory_id, is_sensitive, reopen_count, close_reason, resolved_at,"
    " closed_at, created_by_user_id, operation_id, created_at, updated_at"
)


class ServiceCaseRepository(CustomerServiceRepositoryBase):
    def next_code(self) -> ServiceCaseCode:
        last = self._scalar(
            "SELECT case_number FROM service_cases"
            " ORDER BY CAST(SUBSTR(case_number, 6) AS INTEGER) DESC LIMIT 1")
        seq = (int(last.split("-")[1]) + 1) if last else 1
        return ServiceCaseCode.from_sequence(seq)

    def save(self, case: CustomerServiceCase, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO service_cases ({_CASE_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(case, operation_id or case.operation_id))

    def update(self, case: CustomerServiceCase) -> None:
        self._execute(
            "UPDATE service_cases SET subject=?, status=?, priority=?, category_id=?,"
            " description=?, assigned_user_id=?, is_sensitive=?, reopen_count=?,"
            " close_reason=?, resolved_at=?, closed_at=?, updated_at=? WHERE id=?",
            (case.subject, case.status.value, case.priority.value, case.category_id,
             case.description, case.assigned_user_id, int(case.is_sensitive),
             case.reopen_count, case.close_reason, case.resolved_at, case.closed_at,
             case.updated_at, case.id))

    def get(self, case_id: str) -> CustomerServiceCase | None:
        row = self._query_one(f"SELECT {_CASE_COLS} FROM service_cases WHERE id=?", (case_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> CustomerServiceCase | None:
        row = self._query_one(f"SELECT {_CASE_COLS} FROM service_cases WHERE case_number=?",
                              (code,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> CustomerServiceCase | None:
        row = self._query_one(
            f"SELECT {_CASE_COLS} FROM service_cases WHERE operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    def list_owned_by(self, owner_user_ids: tuple[str, ...], *,
                       limit: int = 200, offset: int = 0) -> list[CustomerServiceCase]:
        if not owner_user_ids:
            return []
        placeholders = ",".join("?" for _ in owner_user_ids)
        rows = self._query(
            f"SELECT {_CASE_COLS} FROM service_cases WHERE assigned_user_id IN ({placeholders})"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*owner_user_ids, limit, offset))
        return [self._hydrate(r) for r in rows]

    def list_open_owned_by(self, owner_user_ids: tuple[str, ...], *,
                            limit: int = 500, offset: int = 0) -> list[CustomerServiceCase]:
        if not owner_user_ids:
            return []
        placeholders = ",".join("?" for _ in owner_user_ids)
        rows = self._query(
            f"SELECT {_CASE_COLS} FROM service_cases WHERE assigned_user_id IN ({placeholders})"
            " AND status NOT IN ('CLOSED','CANCELLED') ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*owner_user_ids, limit, offset))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(case: CustomerServiceCase, operation_id: str | None) -> tuple:
        return (
            case.id, str(case.code), case.customer_id, case.case_type.value, case.subject,
            case.status.value, case.priority.value, case.category_id, case.description,
            case.assigned_user_id, case.channel.value, case.origin_branch_id,
            case.territory_id, int(case.is_sensitive), case.reopen_count, case.close_reason,
            case.resolved_at, case.closed_at, case.created_by_user_id, operation_id,
            case.created_at, case.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerServiceCase:
        return CustomerServiceCase(
            id=row["id"], code=ServiceCaseCode(row["case_number"]), customer_id=row["customer_id"],
            case_type=ServiceCaseType(row["case_type"]), subject=row["subject"],
            status=ServiceCaseStatus(row["status"]), priority=ServiceCasePriority(row["priority"]),
            category_id=row["category_id"], description=row["description"] or "",
            assigned_user_id=row["assigned_user_id"], channel=ServiceCaseChannel(row["channel"]),
            origin_branch_id=row["origin_branch_id"], territory_id=row["territory_id"],
            is_sensitive=bool(row["is_sensitive"]), reopen_count=row["reopen_count"],
            close_reason=row["close_reason"] or "", resolved_at=row["resolved_at"],
            closed_at=row["closed_at"], created_by_user_id=row["created_by_user_id"],
            operation_id=row["operation_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
