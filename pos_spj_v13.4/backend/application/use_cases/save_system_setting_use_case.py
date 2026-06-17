"""Save system setting use case."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveSystemSettingCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class SaveSystemSettingUseCase(DelegatingUseCase[SaveSystemSettingCommand]):
    name = "SaveSystemSettingUseCase"
