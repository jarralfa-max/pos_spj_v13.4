"""SQLite repository for HR attendance adjustments."""

from __future__ import annotations

from datetime import datetime
from sqlite3 import Connection

from backend.domain.hr.entities import AttendanceAdjustment
from backend.domain.hr.enums import AdjustmentStatus


def _adjustment_from_row(row) -> AttendanceAdjustment:
    return AttendanceAdjustment(
        id=row[0],
        original_punch_id=row[1],
        requested_value=datetime.fromisoformat(row[2]),
        previous_value=datetime.fromisoformat(row[3]),
        reason=row[4],
        requested_by_user_id=row[5],
        approved_by_user_id=row[6],
        status=AdjustmentStatus(row[7]),
        created_at=datetime.fromisoformat(row[8]),
        approved_at=datetime.fromisoformat(row[9]) if row[9] else None,
    )


class SQLiteAttendanceAdjustmentRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save(self, adjustment: AttendanceAdjustment) -> None:
        self._connection.execute(
            """
            INSERT INTO attendance_adjustments (
                id, original_punch_id, requested_value, previous_value, reason,
                requested_by_user_id, approved_by_user_id, status, created_at, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                adjustment.id,
                adjustment.original_punch_id,
                adjustment.requested_value.isoformat(),
                adjustment.previous_value.isoformat(),
                adjustment.reason,
                adjustment.requested_by_user_id,
                adjustment.approved_by_user_id,
                adjustment.status.value,
                adjustment.created_at.isoformat(),
                adjustment.approved_at.isoformat() if adjustment.approved_at else None,
            ),
        )

    def get(self, adjustment_id: str) -> AttendanceAdjustment | None:
        row = self._connection.execute(
            """
            SELECT id, original_punch_id, requested_value, previous_value, reason,
                   requested_by_user_id, approved_by_user_id, status, created_at, approved_at
            FROM attendance_adjustments WHERE id = ?
            """,
            (adjustment_id,),
        ).fetchone()
        return _adjustment_from_row(row) if row else None

    def update_status(self, adjustment: AttendanceAdjustment) -> None:
        self._connection.execute(
            """
            UPDATE attendance_adjustments
            SET approved_by_user_id = ?, status = ?, approved_at = ?
            WHERE id = ?
            """,
            (
                adjustment.approved_by_user_id,
                adjustment.status.value,
                adjustment.approved_at.isoformat() if adjustment.approved_at else None,
                adjustment.id,
            ),
        )
