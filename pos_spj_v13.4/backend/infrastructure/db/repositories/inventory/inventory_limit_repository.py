"""InventoryLimitRepository — reads configurable operation limits (§48).

Limits live in ``inventory_operation_limits`` scoped to user/role/branch/
warehouse per operation kind; the policy layer decides WITHIN / REQUIRES_APPROVAL
/ EXCEEDS from them. ``resolve`` picks the most specific configured scope.
"""

from __future__ import annotations

from backend.domain.inventory.enums import LimitBasis
from backend.domain.inventory.value_objects.inventory_limit import (
    InventoryOperationLimit,
)
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    now_iso,
    opt_dec_str,
    to_decimal,
)
from backend.shared.ids import new_uuid

_SCOPE_PRECEDENCE = ("USER", "ROLE", "WAREHOUSE", "BRANCH")


def _to_limit(row: dict) -> InventoryOperationLimit:
    def _opt(key):
        v = row.get(key)
        return to_decimal(v) if v not in (None, "") else None
    return InventoryOperationLimit(
        basis=LimitBasis(row.get("basis") or "QUANTITY"),
        warning_threshold=_opt("warning_threshold"),
        approval_threshold=_opt("approval_threshold"),
        hard_cap=_opt("hard_cap"))


class InventoryLimitRepository(InventoryRepositoryBase):
    def get_limit(self, *, scope_type: str, scope_id: str,
                  operation_kind: str) -> InventoryOperationLimit | None:
        row = self._query_one(
            "SELECT * FROM inventory_operation_limits WHERE scope_type=? AND scope_id=?"
            " AND operation_kind=? AND active=1",
            (scope_type, scope_id, operation_kind))
        return _to_limit(row) if row else None

    def upsert_limit(self, *, scope_type: str, scope_id: str, operation_kind: str,
                     limit: InventoryOperationLimit) -> None:
        self._execute(
            "INSERT INTO inventory_operation_limits (id, scope_type, scope_id,"
            " operation_kind, basis, warning_threshold, approval_threshold, hard_cap,"
            " active, created_at) VALUES (?,?,?,?,?,?,?,?,1,?)"
            " ON CONFLICT(scope_type, scope_id, operation_kind) DO UPDATE SET"
            " basis=excluded.basis, warning_threshold=excluded.warning_threshold,"
            " approval_threshold=excluded.approval_threshold, hard_cap=excluded.hard_cap,"
            " active=1",
            (new_uuid(), scope_type, scope_id, operation_kind, limit.basis.value,
             opt_dec_str(limit.warning_threshold), opt_dec_str(limit.approval_threshold),
             opt_dec_str(limit.hard_cap), now_iso()))

    def resolve(self, *, operation_kind: str, user_id: str | None = None,
                role_code: str | None = None, warehouse_id: str | None = None,
                branch_id: str | None = None) -> InventoryOperationLimit | None:
        scope_ids = {"USER": user_id, "ROLE": role_code,
                     "WAREHOUSE": warehouse_id, "BRANCH": branch_id}
        for scope_type in _SCOPE_PRECEDENCE:
            scope_id = scope_ids.get(scope_type)
            if not scope_id:
                continue
            limit = self.get_limit(scope_type=scope_type, scope_id=scope_id,
                                   operation_kind=operation_kind)
            if limit is not None:
                return limit
        return None
