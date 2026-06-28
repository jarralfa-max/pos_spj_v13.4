"""Read-only query service for configuration module toggles."""

from __future__ import annotations

import logging
from typing import Any

from repositories.feature_flag_repository import FeatureFlagRepository

logger = logging.getLogger("spj.module_settings.query")


class ModuleSettingsQueryService:
    """Provides branch selectors and feature-flag snapshots without SQL in PyQt."""

    def __init__(self, db_conn: Any, feature_flag_repository: FeatureFlagRepository | None = None) -> None:
        self._db = db_conn
        self._feature_flag_repository = feature_flag_repository or FeatureFlagRepository(db_conn)

    def list_active_branch_options(self) -> list[tuple[str, str]]:
        try:
            rows = self._db.execute(
                "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre"
            ).fetchall()
        except Exception:
            logger.exception("Unable to load active branches for module settings")
            return []
        # sucursales.id es la identidad UUIDv7 (REGLA CERO): no se castea a int.
        return [(str(row[0]), str(row[1])) for row in rows]

    def get_branch_feature_flags(self, branch_id: Any) -> dict[str, bool]:
        normalized_branch_id = self._normalize_branch_id(branch_id)
        if normalized_branch_id is None:
            return {}
        try:
            return self._feature_flag_repository.get_flags_by_branch(normalized_branch_id)
        except Exception:
            logger.exception("Unable to load feature flags for branch=%s", branch_id)
            return {}

    def _normalize_branch_id(self, branch_id: Any) -> str | None:
        # La identidad de sucursal es UUIDv7 TEXT (sucursales.id); el branch_id se
        # propaga tal cual, sin castear a entero ni resolver vía columna 'uuid'
        # legacy (identidad dual eliminada).
        if branch_id in (None, ""):
            return None
        return str(branch_id).strip()
