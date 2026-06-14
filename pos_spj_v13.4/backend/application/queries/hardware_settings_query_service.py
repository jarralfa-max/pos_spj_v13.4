"""Read-only query service for POS hardware settings."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("spj.hardware.settings")


class HardwareSettingsQueryService:
    """Loads hardware settings from the canonical hardware configuration table."""

    def __init__(self, db_conn: Any) -> None:
        self._db = db_conn

    def list_active_configs(self) -> list[dict]:
        try:
            rows = self._db.execute(
                "SELECT tipo, COALESCE(activo,1) as activo, configuraciones FROM hardware_config"
            ).fetchall()
        except Exception:
            logger.exception("Unable to load hardware settings")
            return []
        out: list[dict] = []
        for row in rows:
            tipo = row[0] if not hasattr(row, "keys") else row["tipo"]
            active = row[1] if not hasattr(row, "keys") else row["activo"]
            raw_config = row[2] if not hasattr(row, "keys") else row["configuraciones"]
            try:
                config = json.loads(raw_config) if raw_config else {}
            except Exception:
                logger.exception("Invalid hardware JSON for tipo=%s", tipo)
                config = {}
            out.append({"type": str(tipo), "active": bool(active), "config": config})
        return out
