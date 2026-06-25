from __future__ import annotations

import json
from typing import Any

from core.delivery.infrastructure.delivery_schema_migrator import DeliverySchemaMigrator


class DeliveryOutboxRepository:
    """SQLite repository for transactional delivery outbox events."""

    def __init__(self, db) -> None:
        if db is None:
            raise ValueError("DeliveryOutboxRepository requiere una conexión SQLite válida.")
        self.db = db
        DeliverySchemaMigrator(db).ensure_schema()

    def enqueue(
        self,
        *,
        event_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        aggregate_type: str = "delivery_order",
        operation_id: str | None = None,
        commit: bool = False,
    ) -> int:
        clean_payload = self._without_db(payload)
        effective_operation_id = operation_id or clean_payload.get("operation_id")
        if effective_operation_id:
            existing = self.db.execute(
                """
                SELECT id FROM delivery_outbox_events
                WHERE event_type=? AND aggregate_id=? AND operation_id=?
                LIMIT 1
                """,
                (event_type, str(aggregate_id), str(effective_operation_id)),
            ).fetchone()
            if existing:
                return int(existing[0])
        cur = self.db.execute(
            """
            INSERT INTO delivery_outbox_events(
                event_type, aggregate_type, aggregate_id, payload_json,
                status, retries, operation_id
            ) VALUES(?,?,?,?, 'pending', 0, ?)
            """,
            (
                event_type,
                aggregate_type,
                str(aggregate_id),
                json.dumps(clean_payload, ensure_ascii=False, sort_keys=True),
                str(effective_operation_id) if effective_operation_id else None,
            ),
        )
        if commit:
            self.db.commit()
        return int(cur.lastrowid)

    def fetch_pending(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT * FROM delivery_outbox_events
            WHERE status='pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def mark_done(self, event_id: int, *, commit: bool = True) -> None:
        self.db.execute(
            """
            UPDATE delivery_outbox_events
            SET status='done', processed_at=datetime('now'), last_error=NULL
            WHERE id=?
            """,
            (int(event_id),),
        )
        if commit:
            self.db.commit()

    def mark_error(self, event_id: int, error: str, *, commit: bool = True) -> None:
        self.db.execute(
            """
            UPDATE delivery_outbox_events
            SET retries=COALESCE(retries, 0) + 1, last_error=?, status='pending'
            WHERE id=?
            """,
            (str(error)[:1000], int(event_id)),
        )
        if commit:
            self.db.commit()

    def payload_for(self, event_id: int) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT payload_json FROM delivery_outbox_events WHERE id=?",
            (int(event_id),),
        ).fetchone()
        if not row:
            return None
        return json.loads(row[0] or "{}")

    def _row_to_dict(self, row) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.get("payload_json") or "{}")
        return data

    def _without_db(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._without_db(v) for k, v in value.items() if k != "db"}
        if isinstance(value, list):
            return [self._without_db(v) for v in value]
        if isinstance(value, tuple):
            return [self._without_db(v) for v in value]
        return value
