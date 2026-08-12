"""AuditQueryService — the read the Auditoría UI consults (§20.3 / §47).

Read-only projection over ``inventory_audit_log``: lists recent audit entries
(most recent first, bounded), optionally scoped to a branch — who did what to
which entity, when, and who authorized it. It never writes; the audit trail is
append-only, written by the use cases.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    zn,
)


class AuditQueryService(InventoryRepositoryBase):
    def list_recent(self, *, branch_id: str | None = None,
                    entity_id: str | None = None,
                    limit: int = 200) -> list[dict]:
        """Recent audit entries (most recent first, bounded). Rows carry the
        timestamp, entity type, action, user and authorizer for display.
        ``entity_id`` narrows the trail to one entity (e.g. one movement's
        history — posted, reversed, by whom) instead of the whole branch log."""
        cols = ("occurred_at, entity_type, entity_id, action, user_id,"
                " authorized_by, reason")
        lim = max(1, int(limit))
        if entity_id:
            rows = self._query(
                f"SELECT {cols} FROM inventory_audit_log WHERE entity_id=?"
                " ORDER BY occurred_at DESC, id DESC LIMIT ?", (entity_id, lim))
        elif branch_id:
            rows = self._query(
                f"SELECT {cols} FROM inventory_audit_log WHERE branch_id=?"
                " ORDER BY occurred_at DESC, id DESC LIMIT ?", (branch_id, lim))
        else:
            rows = self._query(
                f"SELECT {cols} FROM inventory_audit_log"
                " ORDER BY occurred_at DESC, id DESC LIMIT ?", (lim,))
        return [{
            "occurred_at": r["occurred_at"], "entity_type": r["entity_type"],
            "entity_id": r["entity_id"], "action": r["action"],
            "user_id": zn(r["user_id"]), "authorized_by": zn(r["authorized_by"]),
            "reason": zn(r["reason"]),
        } for r in rows]
