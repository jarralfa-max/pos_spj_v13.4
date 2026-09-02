"""SqliteFeatureFlagChangeRequestRepository — persists
`FeatureFlagChangeRequest` (SET-21). Implements
`backend.domain.feature_flags.repository_ports.FeatureFlagChangeRequestRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.feature_flags.entities.feature_flag_change_request import FeatureFlagChangeRequest
from backend.domain.feature_flags.enums import FeatureFlagChangeStatus, FeatureFlagScopeType
from backend.infrastructure.db.repositories.feature_flags.base import FeatureFlagsRepositoryBase

_COLS = (
    "id, flag_id, scope_type, scope_id, proposed_enabled, proposed_rollout_percentage,"
    " requested_by_user_id, status, approved_by_user_id, reason, created_at, updated_at"
)


class SqliteFeatureFlagChangeRequestRepository(FeatureFlagsRepositoryBase):
    def save(self, request: FeatureFlagChangeRequest) -> None:
        self._execute(
            f"INSERT INTO ff_change_requests ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " status=excluded.status, approved_by_user_id=excluded.approved_by_user_id,"
            " reason=excluded.reason, updated_at=excluded.updated_at",
            self._params(request),
        )

    def get(self, request_id: str) -> FeatureFlagChangeRequest | None:
        row = self._query_one(f"SELECT {_COLS} FROM ff_change_requests WHERE id=?", (request_id,))
        return self._hydrate(row) if row else None

    def list_pending(self) -> list[FeatureFlagChangeRequest]:
        rows = self._query(
            f"SELECT {_COLS} FROM ff_change_requests WHERE status=? ORDER BY created_at",
            (FeatureFlagChangeStatus.PENDING_APPROVAL.value,),
        )
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(request: FeatureFlagChangeRequest) -> tuple:
        return (
            request.id, request.flag_id, request.scope_type.value, request.scope_id,
            int(request.proposed_enabled), request.proposed_rollout_percentage,
            request.requested_by_user_id, request.status.value, request.approved_by_user_id,
            request.reason, request.created_at, request.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> FeatureFlagChangeRequest:
        return FeatureFlagChangeRequest(
            id=row["id"], flag_id=row["flag_id"], scope_type=FeatureFlagScopeType(row["scope_type"]),
            scope_id=row["scope_id"], proposed_enabled=bool(row["proposed_enabled"]),
            proposed_rollout_percentage=row["proposed_rollout_percentage"],
            requested_by_user_id=row["requested_by_user_id"], status=FeatureFlagChangeStatus(row["status"]),
            approved_by_user_id=row["approved_by_user_id"], reason=row["reason"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
