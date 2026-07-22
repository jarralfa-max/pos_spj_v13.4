"""Notification repositories (§55, INV-23).

RuleRepository stores routing rules; LogRepository is the audit trail, the
idempotency guard (UNIQUE dedupe_key) and the throttle source.
"""

from __future__ import annotations

from backend.domain.inventory.entities.notification_rule import NotificationRule
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    enum_value,
    now_iso,
)
from backend.shared.ids import new_uuid


class NotificationRuleRepository(InventoryRepositoryBase):
    def upsert(self, rule: NotificationRule) -> None:
        self._execute(
            "INSERT INTO inventory_notification_rule (id, event_name, scope_type,"
            " scope_id, channel, recipient_type, recipient_ref, min_severity,"
            " throttle_seconds, active, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(event_name, scope_type, scope_id, channel, recipient_ref)"
            " DO UPDATE SET min_severity=excluded.min_severity,"
            " recipient_type=excluded.recipient_type,"
            " throttle_seconds=excluded.throttle_seconds, active=excluded.active",
            (rule.id, rule.event_name, rule.scope_type, rule.scope_id,
             enum_value(rule.channel), enum_value(rule.recipient_type),
             rule.recipient_ref, enum_value(rule.min_severity), rule.throttle_seconds,
             1 if rule.active else 0, rule.created_at))

    def list_for_event(self, event_name: str) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_notification_rule WHERE event_name=? AND active=1"
            " ORDER BY created_at", (event_name,))


class NotificationLogRepository(InventoryRepositoryBase):
    def exists(self, dedupe_key: str) -> bool:
        return self._query_one(
            "SELECT id FROM inventory_notification_log WHERE dedupe_key=?",
            (dedupe_key,)) is not None

    def last_sent_at(self, *, event_name: str, channel: str, recipient_ref: str) -> str | None:
        return self._scalar(
            "SELECT MAX(created_at) FROM inventory_notification_log WHERE event_name=?"
            " AND channel=? AND recipient_ref=? AND status='SENT'",
            (event_name, channel, recipient_ref))

    def record(self, *, event_id: str, event_name: str, rule_id: str | None,
               channel: str, recipient_ref: str, severity: str, status: str,
               dedupe_key: str, message: str = "", branch_id: str | None = None,
               warehouse_id: str | None = None, product_id: str | None = None,
               created_at: str | None = None) -> str:
        row_id = new_uuid()
        self._execute(
            "INSERT INTO inventory_notification_log (id, event_id, event_name, rule_id,"
            " channel, recipient_ref, severity, status, dedupe_key, message, branch_id,"
            " warehouse_id, product_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row_id, event_id, event_name, rule_id, channel, recipient_ref, severity,
             status, dedupe_key, message[:500], branch_id, warehouse_id, product_id,
             created_at or now_iso()))
        return row_id

    def list_for_event(self, event_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_notification_log WHERE event_id=?"
            " ORDER BY created_at", (event_id,))
