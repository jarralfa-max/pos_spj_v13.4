"""Save SMTP settings use case."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveSMTPSettingsCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class SaveSMTPSettingsUseCase(DelegatingUseCase[SaveSMTPSettingsCommand]):
    name = "SaveSMTPSettingsUseCase"
