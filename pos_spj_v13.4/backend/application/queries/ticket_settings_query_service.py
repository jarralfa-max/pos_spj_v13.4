"""Read-only query service for visual ticket settings."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("spj.ticket.settings")


class TicketSettingsQueryService:
    """Provides ticket template/settings without SQL in UI."""

    def __init__(self, db_conn: Any, config_service: Any | None = None) -> None:
        self._db = db_conn
        self._config_service = config_service

    def get(self, key: str, default: str = "") -> str:
        if self._config_service is not None:
            value = self._config_service.get(key, default)
            return value if value else default
        try:
            row = self._db.execute("SELECT valor FROM configuraciones WHERE clave=?", (key,)).fetchone()
        except Exception:
            logger.exception("Unable to load ticket setting key=%s", key)
            return default
        value = row[0] if row and row[0] else default
        return str(value)
