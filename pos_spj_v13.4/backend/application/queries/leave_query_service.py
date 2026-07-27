"""Read-only query service for HR leave requests."""

from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

from backend.application.dto.leave_dto import LeaveHistoryDTO, LeaveRequestDTO


class LeaveQueryService:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_requests(self, *, branch_id: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> list[LeaveRequestDTO]:
        clauses: list[str] = []
        params: list[object] = []
        if branch_id:
            clauses.append("branch_id = ?")
            params.append(branch_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.extend([limit, offset])
        rows = self._connection.execute(
            """
            SELECT id, employee_id, branch_id, leave_type, start_date, end_date,
                   requested_days, reason, status
            FROM leave_requests
            """
            + where
            + " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            tuple(params),
        ).fetchall()
        return [self._row_to_dto(row) for row in rows]

    def list_pending(self, *, limit: int = 50, offset: int = 0) -> list[LeaveRequestDTO]:
        return self.list_requests(status="PENDING", limit=limit, offset=offset)

    def list_history(self, *, leave_request_id: str) -> list[LeaveHistoryDTO]:
        rows = self._connection.execute(
            """
            SELECT id, leave_request_id, previous_status, new_status, actor_user_id, reason, operation_id, created_at
            FROM leave_request_history
            WHERE leave_request_id = ?
            ORDER BY created_at
            """,
            (leave_request_id,),
        ).fetchall()
        return [
            LeaveHistoryDTO(
                id=row[0],
                leave_request_id=row[1],
                previous_status=row[2],
                new_status=row[3],
                actor_user_id=row[4],
                reason=row[5],
                operation_id=row[6],
                created_at=row[7],
            )
            for row in rows
        ]

    def _row_to_dto(self, row) -> LeaveRequestDTO:
        return LeaveRequestDTO(
            id=row[0],
            employee_id=row[1],
            branch_id=row[2],
            leave_type=row[3],
            start_date=row[4],
            end_date=row[5],
            requested_days=Decimal(str(row[6])),
            reason=row[7],
            status=row[8],
        )
