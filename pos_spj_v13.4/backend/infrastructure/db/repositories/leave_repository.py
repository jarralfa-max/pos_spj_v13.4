"""SQLite repository for HR leave requests, balances and history."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from sqlite3 import Connection

from backend.domain.hr.entities import LeaveRequest
from backend.domain.hr.enums import LeaveStatus, LeaveType
from backend.shared.ids import new_uuid


class SQLiteLeaveRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save(self, leave_request: LeaveRequest) -> None:
        self._connection.execute(
            """
            INSERT INTO leave_requests (
                id, employee_id, branch_id, leave_type, start_date, end_date,
                requested_days, reason, status, requested_by_user_id,
                approved_by_user_id, approved_at, operation_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(operation_id) DO NOTHING
            """,
            self._params(leave_request),
        )

    def update(self, leave_request: LeaveRequest) -> None:
        self._connection.execute(
            """
            UPDATE leave_requests
            SET status = ?, approved_by_user_id = ?, approved_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                leave_request.status.value,
                leave_request.approved_by_user_id,
                leave_request.approved_at.isoformat() if leave_request.approved_at else None,
                leave_request.updated_at.isoformat(),
                leave_request.id,
            ),
        )

    def get(self, leave_request_id: str) -> LeaveRequest | None:
        row = self._connection.execute(
            """
            SELECT id, employee_id, branch_id, leave_type, start_date, end_date,
                   requested_days, reason, status, requested_by_user_id,
                   approved_by_user_id, approved_at, operation_id, created_at, updated_at
            FROM leave_requests
            WHERE id = ?
            """,
            (leave_request_id,),
        ).fetchone()
        return self._row_to_leave(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> LeaveRequest | None:
        row = self._connection.execute(
            """
            SELECT id, employee_id, branch_id, leave_type, start_date, end_date,
                   requested_days, reason, status, requested_by_user_id,
                   approved_by_user_id, approved_at, operation_id, created_at, updated_at
            FROM leave_requests
            WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        return self._row_to_leave(row) if row else None

    def list_overlapping(self, *, employee_id: str, start_date: date, end_date: date, statuses: tuple[LeaveStatus, ...]) -> list[LeaveRequest]:
        status_values = tuple(status.value for status in statuses)
        placeholders = ",".join("?" for _ in status_values)
        rows = self._connection.execute(
            f"""
            SELECT id, employee_id, branch_id, leave_type, start_date, end_date,
                   requested_days, reason, status, requested_by_user_id,
                   approved_by_user_id, approved_at, operation_id, created_at, updated_at
            FROM leave_requests
            WHERE employee_id = ?
              AND status IN ({placeholders})
              AND start_date <= ?
              AND end_date >= ?
            ORDER BY start_date
            """,
            (employee_id, *status_values, end_date.isoformat(), start_date.isoformat()),
        ).fetchall()
        return [self._row_to_leave(row) for row in rows]

    def get_available_days(self, *, employee_id: str, branch_id: str, leave_type: LeaveType) -> Decimal:
        row = self._connection.execute(
            """
            SELECT available_days
            FROM leave_balances
            WHERE employee_id = ? AND branch_id = ? AND leave_type = ?
            """,
            (employee_id, branch_id, leave_type.value),
        ).fetchone()
        return Decimal(str(row[0])) if row else Decimal("0")

    def set_balance(self, *, employee_id: str, branch_id: str, leave_type: LeaveType, available_days: Decimal, accrued_days: Decimal | None = None, used_days: Decimal | None = None) -> None:
        self._connection.execute(
            """
            INSERT INTO leave_balances (id, employee_id, branch_id, leave_type, available_days, accrued_days, used_days, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, branch_id, leave_type) DO UPDATE SET
                available_days = excluded.available_days,
                accrued_days = excluded.accrued_days,
                used_days = excluded.used_days,
                updated_at = excluded.updated_at
            """,
            (
                new_uuid(),
                employee_id,
                branch_id,
                leave_type.value,
                str(available_days),
                str(accrued_days if accrued_days is not None else available_days),
                str(used_days if used_days is not None else Decimal("0")),
                datetime.now(UTC).isoformat(),
            ),
        )

    def debit_balance(self, *, employee_id: str, branch_id: str, leave_type: LeaveType, days: Decimal) -> None:
        current = self.get_available_days(employee_id=employee_id, branch_id=branch_id, leave_type=leave_type)
        self.set_balance(employee_id=employee_id, branch_id=branch_id, leave_type=leave_type, available_days=current - days, used_days=days)

    def add_history(self, *, leave_request_id: str, previous_status: LeaveStatus | None, new_status: LeaveStatus, actor_user_id: str | None, reason: str | None, operation_id: str) -> str:
        history_id = new_uuid()
        self._connection.execute(
            """
            INSERT INTO leave_request_history (id, leave_request_id, previous_status, new_status, actor_user_id, reason, operation_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                history_id,
                leave_request_id,
                previous_status.value if previous_status else None,
                new_status.value,
                actor_user_id,
                reason,
                operation_id,
                datetime.now(UTC).isoformat(),
            ),
        )
        return history_id

    def _params(self, leave_request: LeaveRequest) -> tuple[object, ...]:
        return (
            leave_request.id,
            leave_request.employee_id,
            leave_request.branch_id,
            leave_request.leave_type.value,
            leave_request.start_date.isoformat(),
            leave_request.end_date.isoformat(),
            str(leave_request.requested_days),
            leave_request.reason,
            leave_request.status.value,
            leave_request.requested_by_user_id,
            leave_request.approved_by_user_id,
            leave_request.approved_at.isoformat() if leave_request.approved_at else None,
            leave_request.operation_id,
            leave_request.created_at.isoformat(),
            leave_request.updated_at.isoformat(),
        )

    def _row_to_leave(self, row) -> LeaveRequest:
        return LeaveRequest(
            id=row[0],
            employee_id=row[1],
            branch_id=row[2],
            leave_type=LeaveType(row[3]),
            start_date=date.fromisoformat(row[4]),
            end_date=date.fromisoformat(row[5]),
            requested_days=Decimal(str(row[6])),
            reason=row[7],
            status=LeaveStatus(row[8]),
            requested_by_user_id=row[9],
            approved_by_user_id=row[10],
            approved_at=datetime.fromisoformat(row[11]) if row[11] else None,
            operation_id=row[12],
            created_at=datetime.fromisoformat(row[13]),
            updated_at=datetime.fromisoformat(row[14]),
        )
