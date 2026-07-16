"""SQLite repository for HR positions."""

from __future__ import annotations

from sqlite3 import Connection

from backend.domain.hr.entities import Position


class SQLitePositionRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save(self, position: Position) -> None:
        self._connection.execute(
            """
            INSERT INTO positions (id, name, department_id, active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                department_id = excluded.department_id,
                active = excluded.active
            """,
            (position.id, position.name, position.department_id, 1 if position.active else 0),
        )
