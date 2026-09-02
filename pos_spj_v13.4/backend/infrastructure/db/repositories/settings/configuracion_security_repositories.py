"""Configuración security repositories — SET-1 (§60 "Auditoría en
caliente"). Mirrors `backend.infrastructure.db.repositories.inventory.
support_repositories`'s `InventoryAuthorizationLogRepository`/
`InventoryAuditRepository` shape, same "each bounded context owns its
own log" discipline as Inventory/Products.

Callers must mask sensitive fields before passing `before_json`/
`after_json` (see `backend/security/audit/sensitive_data_redaction.py::
redact_mapping`) — these repositories store whatever they're given
verbatim. Repositories never commit; the caller's unit of work does.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.settings.value_objects.authorization_grant import AuthorizationGrant
from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase
from backend.shared.ids import new_uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConfiguracionAuthorizationLogRepository(SettingsRepositoryBase):
    """Immutable log of hot authorizations: who authorized which
    exception, requested by whom, and why."""

    def record(self, grant: AuthorizationGrant) -> str:
        row_id = new_uuid()
        self._execute(
            "INSERT INTO configuracion_authorization_log (id, permission_code, requested_by,"
            " authorized_by, operation_id, reason, device_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (row_id, grant.permission_code, grant.requested_by, grant.authorized_by,
             grant.operation_id, grant.reason, grant.device_id, _now_iso()),
        )
        return row_id

    def list_for_operation(self, operation_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM configuracion_authorization_log WHERE operation_id = ?"
            " ORDER BY created_at",
            (operation_id,),
        )


class ConfiguracionAuditLogRepository(SettingsRepositoryBase):
    """Before/after audit trail for critical Configuración mutations
    (device status changes, template version status changes)."""

    def record(
        self, *, entity_type: str, entity_id: str, action: str,
        user_id: str | None = None, authorized_by: str | None = None,
        operation_id: str | None = None, before_json: str | None = None,
        after_json: str | None = None, reason: str | None = None,
        branch_id: str | None = None, device_id: str | None = None,
        source_module: str = "configuracion",
    ) -> None:
        self._execute(
            "INSERT INTO configuracion_audit_log (id, entity_type, entity_id, action, user_id,"
            " authorized_by, operation_id, before_json, after_json, reason, branch_id,"
            " occurred_at, device_id, source_module) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), entity_type, entity_id, action, user_id, authorized_by,
             operation_id, before_json, after_json, reason, branch_id, _now_iso(),
             device_id, source_module),
        )

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM configuracion_audit_log WHERE entity_type = ? AND entity_id = ?"
            " ORDER BY occurred_at",
            (entity_type, entity_id),
        )
