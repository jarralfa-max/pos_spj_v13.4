"""FinanceSettings repository — clave/valor tipado por ``FinanceSettings``."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.finance.entities.finance_settings import FinanceSettings
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


class FinanceSettingsRepository(FinanceRepositoryBase):
    def load(self) -> FinanceSettings:
        raw = {row["setting_key"]: row["setting_value"] for row in self._query(
            "SELECT setting_key, setting_value FROM finance_settings")}
        return FinanceSettings.from_storage(raw)

    def save(self, settings: FinanceSettings, *, updated_by: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for key, value in settings.as_storage().items():
            self._conn.execute(
                "INSERT INTO finance_settings (setting_key, setting_value, updated_by, updated_at)"
                " VALUES (?,?,?,?) ON CONFLICT(setting_key) DO UPDATE SET"
                " setting_value=excluded.setting_value, updated_by=excluded.updated_by,"
                " updated_at=excluded.updated_at", (key, value, updated_by, now))
