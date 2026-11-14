"""Frontera transaccional de resolver un conflicto de replicación (SDLC-SYNC-002):
el cambio de estado del sobre y su rastro en `audit_logs` se confirman juntos."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.infrastructure.db.repositories.replication.unit_of_work import (
    ReplicationUnitOfWork,
)
from backend.infrastructure.db.repositories.settings.audit_log_repository import (
    SqliteAuditLogRepository,
)


class ReplicationConflictUnitOfWork(ReplicationUnitOfWork):
    def __init__(self, connection: Any) -> None:
        super().__init__(connection)
        self.audit_log = SqliteAuditLogRepository(connection)

    @staticmethod
    def clock_now() -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = ["ReplicationConflictUnitOfWork"]
