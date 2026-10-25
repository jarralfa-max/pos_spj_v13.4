"""Acceso al ``loss_outbox`` para su despacho (Mermas → bus de la aplicación)."""

from __future__ import annotations

from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LossOutboxRepository:
    def __init__(self, connection) -> None:
        self._db = connection

    def deliverable(self, *, max_attempts: int, limit: int) -> list[dict]:
        rows = self._db.execute(
            "SELECT id, event_name, payload_json, attempt_count FROM loss_outbox"
            " WHERE status IN ('PENDING','FAILED') AND attempt_count < ?"
            " ORDER BY created_at LIMIT ?", (max_attempts, limit)).fetchall()
        return [{"id": r[0], "event_name": r[1], "payload_json": r[2], "attempts": r[3]}
                for r in rows]

    def mark_dispatched(self, outbox_id: str) -> None:
        self._db.execute("UPDATE loss_outbox SET status='DISPATCHED', dispatched_at=?,"
                         " last_error=NULL WHERE id=?", (_now(), outbox_id))
        self._db.commit()

    def mark_failed(self, outbox_id: str, error: str, *, dead: bool) -> None:
        self._db.execute(
            "UPDATE loss_outbox SET status=?, attempt_count=attempt_count+1, last_error=?,"
            " next_attempt_at=? WHERE id=?",
            ("DEAD_LETTER" if dead else "FAILED", error[:500], _now(), outbox_id))
        self._db.commit()
