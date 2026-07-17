"""PurchaseLimitRepository — reads configurable purchase limits (§56 §57).

Limits are never hardcoded in UI; they live in user/role/branch tables. The
policy layer decides WITHIN / REQUIRES_APPROVAL / EXCEEDS from these values.
"""

from __future__ import annotations

from datetime import date

from backend.domain.procurement.value_objects import PurchaseLimit
from backend.infrastructure.db.repositories.procurement.base import (
    ProcurementRepositoryBase,
    dec_str,
    to_decimal,
)
from backend.shared.ids import new_uuid


def _limit_from_row(row: dict) -> PurchaseLimit:
    def _opt(key):
        value = row.get(key)
        return to_decimal(value) if value not in (None, "") else None

    return PurchaseLimit(
        currency_code=row.get("currency_code", "MXN"),
        maximum_per_transaction=_opt("maximum_per_transaction"),
        maximum_per_day=_opt("maximum_per_day"),
        maximum_per_month=_opt("maximum_per_month"),
        requires_approval_above=_opt("requires_approval_above"))


class PurchaseLimitRepository(ProcurementRepositoryBase):
    def upsert_user_limit(self, *, user_id: str, limit: PurchaseLimit) -> None:
        self._execute(
            "INSERT INTO user_purchase_limits (id, user_id, currency_code,"
            " maximum_per_transaction, maximum_per_day, maximum_per_month,"
            " requires_approval_above, active) VALUES (?,?,?,?,?,?,?,1)"
            " ON CONFLICT(user_id, currency_code) DO UPDATE SET"
            " maximum_per_transaction=excluded.maximum_per_transaction,"
            " maximum_per_day=excluded.maximum_per_day,"
            " maximum_per_month=excluded.maximum_per_month,"
            " requires_approval_above=excluded.requires_approval_above, active=1",
            (new_uuid(), user_id, limit.currency_code,
             _opt_str(limit.maximum_per_transaction), _opt_str(limit.maximum_per_day),
             _opt_str(limit.maximum_per_month), _opt_str(limit.requires_approval_above)))

    def get_user_limit(self, user_id: str, currency_code: str = "MXN") -> PurchaseLimit | None:
        row = self._query_one(
            "SELECT * FROM user_purchase_limits WHERE user_id=? AND currency_code=?"
            " AND active=1", (user_id, currency_code))
        return _limit_from_row(row) if row else None

    def get_role_limit(self, role_code: str, currency_code: str = "MXN") -> PurchaseLimit | None:
        row = self._query_one(
            "SELECT * FROM role_purchase_limits WHERE role_code=? AND currency_code=?"
            " AND active=1", (role_code, currency_code))
        return _limit_from_row(row) if row else None

    def branch_allows_direct(self, branch_id: str, currency_code: str = "MXN") -> bool:
        row = self._query_one(
            "SELECT allows_direct_purchase FROM branch_purchase_limits"
            " WHERE branch_id=? AND currency_code=? AND active=1",
            (branch_id, currency_code))
        # No configured row → allowed by default (opt-out model).
        return True if row is None else bool(row["allows_direct_purchase"])


def _opt_str(value):
    return None if value is None else dec_str(value)
