"""Support repositories: hot-authorization log, audit log, transactional outbox,
processed-events registry, and scoped settings.

Sensitive fields must never be written raw into audit/outbox payloads — callers
mask them first.
"""

from __future__ import annotations

from backend.domain.inventory.value_objects.authorization_grant import (
    AuthorizationGrant,
)
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    opt_dec_str,
    now_iso,
)
from backend.shared.ids import new_uuid


class InventoryAuthorizationLogRepository(InventoryRepositoryBase):
    """Immutable log of hot authorizations (§48): who authorized which exception."""

    def record(self, grant: AuthorizationGrant) -> str:
        row_id = new_uuid()
        self._execute(
            "INSERT INTO inventory_authorization_log (id, permission_code, requested_by,"
            " authorized_by, operation_id, reason, quantity, weight, value_reference,"
            " device_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (row_id, grant.permission_code, grant.requested_by, grant.authorized_by,
             grant.operation_id, grant.reason, opt_dec_str(grant.quantity),
             opt_dec_str(grant.weight), opt_dec_str(grant.value_reference),
             grant.device_id, now_iso()))
        return row_id


class InventoryAuditRepository(InventoryRepositoryBase):
    def record(self, *, entity_type: str, entity_id: str, action: str,
               user_id: str | None = None, authorized_by: str | None = None,
               operation_id: str | None = None, before_json: str | None = None,
               after_json: str | None = None, reason: str | None = None,
               branch_id: str | None = None, warehouse_id: str | None = None,
               location_id: str | None = None, product_id: str | None = None,
               lot_id: str | None = None, device_id: str | None = None,
               source_module: str = "inventory") -> None:
        self._execute(
            "INSERT INTO inventory_audit_log (id, entity_type, entity_id, action, user_id,"
            " authorized_by, operation_id, before_json, after_json, reason, branch_id,"
            " warehouse_id, location_id, product_id, lot_id, occurred_at, device_id,"
            " source_module) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), entity_type, entity_id, action, user_id, authorized_by,
             operation_id, before_json, after_json, reason, branch_id, warehouse_id,
             location_id, product_id, lot_id, now_iso(), device_id, source_module))

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[dict]:
        return self._query(
            "SELECT action, user_id, authorized_by, reason, occurred_at"
            " FROM inventory_audit_log WHERE entity_type=? AND entity_id=?"
            " ORDER BY occurred_at", (entity_type, entity_id))


class InventoryOutboxRepository(InventoryRepositoryBase):
    """Transactional outbox: events are enqueued in the same transaction as the
    state change, then published post-commit."""

    def enqueue(self, *, event_id: str, event_name: str, payload_json: str,
                operation_id: str) -> None:
        self._execute(
            "INSERT INTO inventory_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, now_iso()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM inventory_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?",
            (limit,))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE inventory_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (now_iso(), outbox_id))


class InventoryProcessedEventRepository(InventoryRepositoryBase):
    def was_processed(self, event_id: str) -> bool:
        return self._query_one(
            "SELECT event_id FROM inventory_processed_events WHERE event_id=?",
            (event_id,)) is not None

    def mark_processed(self, event_id: str, event_name: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO inventory_processed_events (event_id, event_name, operation_id,"
            " processed_at) VALUES (?,?,?,?)",
            (event_id, event_name, operation_id, now_iso()))


class InventorySettingsRepository(InventoryRepositoryBase):
    """Scoped configuration (§56): negative_inventory_allowed, default policies, …"""

    def get(self, *, setting_key: str, scope_type: str = "GLOBAL",
            scope_id: str = "") -> str | None:
        return self._scalar(
            "SELECT setting_value FROM inventory_settings WHERE scope_type=?"
            " AND scope_id=? AND setting_key=?",
            (scope_type, scope_id, setting_key))

    def set(self, *, setting_key: str, setting_value: str, scope_type: str = "GLOBAL",
            scope_id: str = "", created_by_user_id: str | None = None) -> None:
        self._execute(
            "INSERT INTO inventory_settings (id, scope_type, scope_id, setting_key,"
            " setting_value, version, created_by_user_id) VALUES (?,?,?,?,?,1,?)"
            " ON CONFLICT(scope_type, scope_id, setting_key) DO UPDATE SET"
            " setting_value=excluded.setting_value, version=inventory_settings.version+1",
            (new_uuid(), scope_type, scope_id, setting_key, setting_value,
             created_by_user_id))
