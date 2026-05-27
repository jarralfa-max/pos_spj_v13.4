from __future__ import annotations

import json
from typing import Optional

from .ticket_layout_config import TicketLayoutConfig


class TicketLayoutRepository:
    def __init__(self, db_conn=None, config_service=None):
        self.db = db_conn
        self.config_service = config_service

    def _get(self, key: str, default: str = "") -> str:
        if self.config_service is not None:
            v = self.config_service.get(key, default)
            return v if v not in (None, "") else default
        if self.db is None:
            return default
        row = self.db.execute("SELECT valor FROM configuraciones WHERE clave=?", (key,)).fetchone()
        return row[0] if row and row[0] else default

    def _set(self, key: str, value: str) -> None:
        if self.config_service is not None:
            self.config_service.set(key, value)
            return
        if self.db is None:
            return
        self.db.execute("INSERT OR REPLACE INTO configuraciones(clave, valor) VALUES (?,?)", (key, value))
        self.db.commit()

    def load(self) -> TicketLayoutConfig:
        raw = self._get("ticket_layout_config", "")
        if raw:
            try:
                return TicketLayoutConfig.from_dict(json.loads(raw))
            except Exception:
                pass
        legacy = {
            "ticket_paper_width": self._get("ticket_paper_width", "80"),
            "ticket_logo_width": self._get("ticket_logo_width", "150"),
            "ticket_logo_pos": self._get("ticket_logo_pos", "Centrado"),
            "ticket_qr_enabled": self._get("ticket_qr_enabled", "0"),
            "ticket_bc_enabled": self._get("ticket_bc_enabled", "0"),
        }
        return TicketLayoutConfig.from_legacy_config(legacy)

    def save(self, cfg: TicketLayoutConfig) -> None:
        self._set("ticket_layout_config", json.dumps(cfg.to_dict(), ensure_ascii=False))
