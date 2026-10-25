"""ReplicationUnitOfWork — frontera transaccional del motor de replicación."""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.replication.replication_repository import (
    ReplicationRepository,
)
from backend.infrastructure.db.transaction import TransactionalUnitOfWork


class ReplicationUnitOfWork(TransactionalUnitOfWork):
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.replication = ReplicationRepository(connection)
        self._completed = False
