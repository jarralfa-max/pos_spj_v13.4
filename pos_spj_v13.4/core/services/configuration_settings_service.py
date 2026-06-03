"""Application services for the Configuración module.

These services keep schema/default bootstrapping out of PyQt and provide an
explicit backend boundary for configuration reads and mutations.
"""

from __future__ import annotations

from typing import Any

from core.module_config import DEFAULT_TOGGLES
from repositories.config_repository import ConfigRepository


class SystemSettingsService:
    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def ensure_configuration_available(self) -> bool:
        try:
            self._repository.get_all_settings()
            return True
        except Exception:
            return False

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        return self._repository.get_setting(key, default or "")

    def get_many(self, keys: list[str], defaults: dict[str, str] | None = None) -> dict[str, str]:
        defaults = defaults or {}
        values = self._repository.get_settings(keys)
        return {key: str(values.get(key, defaults.get(key, ""))) for key in keys}

    def set_setting(self, key: str, value: Any) -> None:
        self._repository.save_setting(key, str(value))

    def save_many(self, settings: dict[str, Any]) -> None:
        for key, value in settings.items():
            self.set_setting(key, value)


class ModuleSettingsService:
    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository
        self._defaults = dict(DEFAULT_TOGGLES)

    def normalize_key(self, module_key: str) -> str:
        return module_key if module_key.endswith("_enabled") else f"{module_key}_enabled"

    def is_enabled(self, module_key: str) -> bool:
        key = self.normalize_key(module_key)
        return self.get_all().get(key, self._defaults.get(key, True))

    def set_enabled(self, module_key: str, enabled: bool) -> None:
        self._repository.set_module_toggle(self.normalize_key(module_key), enabled)

    def get_all(self) -> dict[str, bool]:
        toggles = dict(self._defaults)
        try:
            toggles.update(self._repository.get_module_toggles())
        except Exception:
            pass
        return toggles


class CompanyProfileService:
    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def get_branch(self, branch_id: int) -> dict | None:
        return self._repository.get_branch(branch_id)

    def save_branch(
        self,
        *,
        name: str,
        address: str | None,
        phone: str | None,
        active: bool,
        branch_id: int | None = None,
    ) -> int:
        return self._repository.save_branch(
            name=name,
            address=address,
            phone=phone,
            active=active,
            branch_id=branch_id,
        )

    def get_branch_delivery_profile(self, branch_id: int) -> dict | None:
        return self._repository.get_branch_delivery_profile(branch_id)

    def save_branch_delivery_profile(
        self,
        *,
        name: str,
        address: str | None,
        phone: str | None,
        opening_time: str,
        closing_time: str,
        operation_days: str,
        accepts_after_hours_orders: bool,
        after_hours_message: str,
        branch_id: int | None = None,
    ) -> int:
        return self._repository.save_branch_delivery_profile(
            name=name,
            address=address,
            phone=phone,
            opening_time=opening_time,
            closing_time=closing_time,
            operation_days=operation_days,
            accepts_after_hours_orders=accepts_after_hours_orders,
            after_hours_message=after_hours_message,
            branch_id=branch_id,
        )


class LoyaltyProgramSettingsService:
    def __init__(self, repository: ConfigRepository) -> None:
        self._repository = repository

    def get_program_config(self) -> dict | None:
        return self._repository.get_loyalty_program_config()

    def save_program_config(
        self,
        *,
        name: str,
        points_per_peso: float,
        levels: str | None,
        requirements: str | None,
        discounts: str | None,
    ) -> None:
        self._repository.save_loyalty_program_config(
            name=name,
            points_per_peso=points_per_peso,
            levels=levels,
            requirements=requirements,
            discounts=discounts,
        )
