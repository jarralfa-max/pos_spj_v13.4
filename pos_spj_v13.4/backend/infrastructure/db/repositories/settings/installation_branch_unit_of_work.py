"""Frontera transaccional del re-anclaje de la estación (SDLC-ARQ-TERM-002).

El ancla (`configuraciones.sucursal_instalacion_id`) y su rastro en
`audit_logs` se confirman juntos o no se confirma nada: un cambio de sucursal
sin auditoría —o una auditoría de un cambio que se revirtió— es justo lo que el
ítem cierra.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.settings.audit_log_repository import (
    SqliteAuditLogRepository,
)
from backend.infrastructure.db.repositories.settings.installation_branch_repository import (
    SqliteInstallationBranchRepository,
)
from backend.infrastructure.db.transaction import TransactionalUnitOfWork


class InstallationBranchUnitOfWork(TransactionalUnitOfWork):
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.installation_branch = SqliteInstallationBranchRepository(connection)
        self.audit_log = SqliteAuditLogRepository(connection)
        self._completed = False


__all__ = ["InstallationBranchUnitOfWork"]
