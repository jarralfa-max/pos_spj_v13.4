"""Persistence for CASH-20 policies, recipients and delivery attempts."""
from __future__ import annotations

import json

from backend.shared.ids import new_uuid


class CashNotificationRepository:
    def __init__(self, connection) -> None:
        self.connection = connection

    def get_event(self, event_id: str):
        cursor = self.connection.execute(
            "SELECT * FROM cash_domain_events WHERE id=?", (event_id,))
        row = cursor.fetchone()
        return None if row is None else dict(zip((item[0] for item in cursor.description), row))

    def resolve_policy(self, *, event_name: str, branch_id: str, occurred_at: str):
        cursor = self.connection.execute(
            """SELECT * FROM cash_alert_rules WHERE event_name=? AND active=1
            AND effective_from<=? AND (effective_to IS NULL OR effective_to>?)
            AND ((scope_type='BRANCH' AND scope_id=?) OR scope_type='SYSTEM')
            ORDER BY CASE scope_type WHEN 'BRANCH' THEN 0 ELSE 1 END,effective_from DESC LIMIT 1""",
            (event_name, occurred_at, occurred_at, branch_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        policy = dict(zip((item[0] for item in cursor.description), row))
        policy["channels"] = tuple(json.loads(policy["channels_json"]))
        return policy

    def recipients(self, *, rule_id: str, channel: str) -> list[str]:
        contracts = {
            "IN_APP": ("cash_in_app_recipients", "user_id"),
            "WHATSAPP": ("cash_whatsapp_recipients", "phone_e164"),
            "EMAIL": ("cash_email_recipients", "email"),
        }
        if channel not in contracts:
            raise ValueError("Unsupported notification channel")
        table, column = contracts[channel]
        return [row[0] for row in self.connection.execute(
            f"SELECT {column} FROM {table} WHERE alert_rule_id=? AND active=1 ORDER BY {column}",
            (rule_id,),
        ).fetchall()]

    def add_job(self, *, source_event_id: str, rule_id: str, channel: str,
                recipient: str, severity: str, title: str, body: str,
                created_at: str) -> bool:
        cursor = self.connection.execute(
            """INSERT INTO cash_notification_jobs
            (id,source_event_id,alert_rule_id,channel,recipient,severity,title,body,status,created_at)
            VALUES(?,?,?,?,?,?,?,?,'PENDING',?)
            ON CONFLICT(source_event_id,channel,recipient) DO NOTHING""",
            (new_uuid(), source_event_id, rule_id, channel, recipient,
             severity, title, body, created_at),
        )
        return cursor.rowcount == 1

    def ready(self, *, now: str, limit: int) -> list[dict]:
        cursor = self.connection.execute(
            """SELECT j.*,e.operation_id,e.entity_id,e.branch_id,e.user_id
            FROM cash_notification_jobs j JOIN cash_domain_events e ON e.id=j.source_event_id
            WHERE j.status IN ('PENDING','RETRY') AND (j.next_attempt_at IS NULL OR j.next_attempt_at<=?)
            ORDER BY j.created_at,j.id LIMIT ?""", (now, limit))
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def claim(self, job_id: str) -> bool:
        cursor = self.connection.execute(
            """UPDATE cash_notification_jobs SET status='PROCESSING',attempt_count=attempt_count+1
            WHERE id=? AND status IN ('PENDING','RETRY')""", (job_id,))
        return cursor.rowcount == 1

    def finish(self, *, job: dict, status: str, attempted_at: str,
               provider_reference: str = "", error_code: str = "",
               next_attempt_at: str | None = None) -> None:
        if status not in {"DELIVERED", "RETRY", "SKIPPED", "DEAD_LETTER"}:
            raise ValueError("Invalid notification result")
        self.connection.execute(
            """UPDATE cash_notification_jobs SET status=?,next_attempt_at=?,last_error=?,
            delivered_at=CASE WHEN ?='DELIVERED' THEN ? ELSE delivered_at END
            WHERE id=? AND status='PROCESSING'""",
            (status, next_attempt_at, error_code or None, status, attempted_at, job["id"]),
        )
        self.connection.execute(
            """INSERT INTO cash_notification_attempts
            (id,job_id,attempt_no,status,provider_reference,error_code,attempted_at)
            VALUES(?,?,?,?,?,?,?)""",
            (new_uuid(), job["id"], int(job["attempt_count"]) + 1, status,
             provider_reference or None, error_code or None, attempted_at),
        )

    def create_in_app_alert(self, *, job: dict, created_at: str) -> None:
        self.connection.execute(
            """INSERT INTO cash_in_app_alerts
            (id,notification_job_id,recipient_user_id,severity,title,body,created_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(notification_job_id) DO NOTHING""",
            (new_uuid(), job["id"], job["recipient"], job["severity"],
             job["title"], job["body"], created_at),
        )

    def unread(self, *, user_id: str, limit: int = 100) -> list[dict]:
        cursor = self.connection.execute(
            """SELECT id,severity,title,body,created_at FROM cash_in_app_alerts
            WHERE recipient_user_id=? AND read_at IS NULL ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
