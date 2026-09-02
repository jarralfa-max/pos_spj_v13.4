"""SqliteCacheExpirationPolicyRepository — persists `CacheExpirationPolicy`
(SET-23). Implements
`backend.domain.offline.repository_ports.CacheExpirationPolicyRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.offline.entities.cache_expiration_policy import CacheExpirationPolicy
from backend.infrastructure.db.repositories.offline.base import OfflineRepositoryBase

_COLS = "id, entity_type, ttl_seconds, active, created_at, updated_at"


class SqliteCacheExpirationPolicyRepository(OfflineRepositoryBase):
    def save(self, policy: CacheExpirationPolicy) -> None:
        self._execute(
            f"INSERT INTO cache_expiration_policies ({_COLS})"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " ttl_seconds=excluded.ttl_seconds, active=excluded.active, updated_at=excluded.updated_at",
            self._params(policy),
        )

    def get(self, policy_id: str) -> CacheExpirationPolicy | None:
        row = self._query_one(f"SELECT {_COLS} FROM cache_expiration_policies WHERE id=?", (policy_id,))
        return self._hydrate(row) if row else None

    def get_by_entity_type(self, entity_type: str) -> CacheExpirationPolicy | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM cache_expiration_policies WHERE entity_type=?", (entity_type.strip(),),
        )
        return self._hydrate(row) if row else None

    def list_active(self) -> list[CacheExpirationPolicy]:
        rows = self._query(f"SELECT {_COLS} FROM cache_expiration_policies WHERE active=1 ORDER BY entity_type")
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[CacheExpirationPolicy]:
        rows = self._query(f"SELECT {_COLS} FROM cache_expiration_policies ORDER BY entity_type")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(policy: CacheExpirationPolicy) -> tuple:
        return (
            policy.id, policy.entity_type, policy.ttl_seconds, int(policy.active), policy.created_at,
            policy.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CacheExpirationPolicy:
        return CacheExpirationPolicy(
            id=row["id"], entity_type=row["entity_type"], ttl_seconds=row["ttl_seconds"],
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )
