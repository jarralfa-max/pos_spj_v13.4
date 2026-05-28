from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class IdempotencyRecord:
    action_key: str
    phone: str
    action_type: str
    status: str
    result_json: str = ""
    error: str = ""

    @property
    def result(self) -> dict:
        if not self.result_json:
            return {}
        try:
            return json.loads(self.result_json)
        except Exception:
            return {}


class BusinessIdempotencyService:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self._ensure_table()

    def _ensure_table(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS wa_business_idempotency (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_key TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        self.db.commit()

    def get(self, action_key: str) -> Optional[IdempotencyRecord]:
        row = self.db.execute(
            """
            SELECT action_key, phone, action_type, status,
                   COALESCE(result_json,''), COALESCE(error,'')
            FROM wa_business_idempotency WHERE action_key=?
            """,
            (action_key,),
        ).fetchone()
        if not row:
            return None
        try:
            return IdempotencyRecord(
                action_key=row["action_key"],
                phone=row["phone"],
                action_type=row["action_type"],
                status=row["status"],
                result_json=row[4] if not isinstance(row, dict) else row.get("result_json", ""),
                error=row[5] if not isinstance(row, dict) else row.get("error", ""),
            )
        except Exception:
            return IdempotencyRecord(*row)

    def start(self, action_key: str, phone: str, action_type: str) -> bool:
        try:
            self.db.execute(
                """
                INSERT INTO wa_business_idempotency(action_key, phone, action_type, status)
                VALUES (?, ?, ?, 'in_progress')
                """,
                (action_key, phone, action_type),
            )
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def complete(self, action_key: str, result: dict) -> None:
        self.db.execute(
            """
            UPDATE wa_business_idempotency
            SET status='completed', result_json=?, error='', updated_at=datetime('now')
            WHERE action_key=?
            """,
            (json.dumps(result, ensure_ascii=False), action_key),
        )
        self.db.commit()

    def fail(self, action_key: str, error: str) -> None:
        self.db.execute(
            """
            UPDATE wa_business_idempotency
            SET status='failed', error=?, updated_at=datetime('now')
            WHERE action_key=?
            """,
            (str(error)[:1000], action_key),
        )
        self.db.commit()

    def run_once(
        self,
        action_key: str,
        phone: str,
        action_type: str,
        callback: Callable[[], dict],
    ) -> dict:
        existing = self.get(action_key)
        if existing and existing.status == "completed":
            return existing.result

        started = self.start(action_key, phone, action_type)
        if not started:
            existing = self.get(action_key)
            if existing and existing.status == "completed":
                return existing.result
            return {"idempotency_status": existing.status if existing else "in_progress"}

        try:
            result = callback() or {}
            if isinstance(result, dict):
                result.setdefault("idempotency_status", "completed")
            self.complete(action_key, result)
            return result
        except Exception as exc:
            self.fail(action_key, str(exc))
            raise
