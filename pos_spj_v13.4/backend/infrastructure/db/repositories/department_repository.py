"""SQLite repository for HR departments."""

from __future__ import annotations

from sqlite3 import Connection

from backend.domain.hr.entities import Department


class SQLiteDepartmentRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save(self, department: Department) -> None:
        self._connection.execute(
            """
            INSERT INTO departments (id, name, branch_id, active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                branch_id = excluded.branch_id,
                active = excluded.active
            """,
            (department.id, department.name, department.branch_id, 1 if department.active else 0),
        )
