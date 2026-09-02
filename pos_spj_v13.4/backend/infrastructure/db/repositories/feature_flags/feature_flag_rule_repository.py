"""SqliteFeatureFlagRuleRepository — persists `FeatureFlagRule` (SET-21).
Implements
`backend.domain.feature_flags.repository_ports.FeatureFlagRuleRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.feature_flags.entities.feature_flag_rule import FeatureFlagRule
from backend.domain.feature_flags.enums import FeatureFlagScopeType
from backend.infrastructure.db.repositories.feature_flags.base import FeatureFlagsRepositoryBase

_COLS = "id, flag_id, scope_type, scope_id, enabled, rollout_percentage, active, created_at, updated_at"


class SqliteFeatureFlagRuleRepository(FeatureFlagsRepositoryBase):
    def save(self, rule: FeatureFlagRule) -> None:
        self._execute(
            f"INSERT INTO ff_rules ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " enabled=excluded.enabled, rollout_percentage=excluded.rollout_percentage,"
            " active=excluded.active, updated_at=excluded.updated_at",
            self._params(rule),
        )

    def get(self, rule_id: str) -> FeatureFlagRule | None:
        row = self._query_one(f"SELECT {_COLS} FROM ff_rules WHERE id=?", (rule_id,))
        return self._hydrate(row) if row else None

    def list_for_flag(self, flag_id: str) -> list[FeatureFlagRule]:
        rows = self._query(f"SELECT {_COLS} FROM ff_rules WHERE flag_id=?", (flag_id,))
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(rule: FeatureFlagRule) -> tuple:
        return (
            rule.id, rule.flag_id, rule.scope_type.value, rule.scope_id, int(rule.enabled),
            rule.rollout_percentage, int(rule.active), rule.created_at, rule.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> FeatureFlagRule:
        return FeatureFlagRule(
            id=row["id"], flag_id=row["flag_id"], scope_type=FeatureFlagScopeType(row["scope_type"]),
            scope_id=row["scope_id"], enabled=bool(row["enabled"]),
            rollout_percentage=row["rollout_percentage"], active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
