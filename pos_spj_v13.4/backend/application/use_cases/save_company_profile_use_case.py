"""Save company profile use case."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveCompanyProfileCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class SaveCompanyProfileUseCase(DelegatingUseCase[SaveCompanyProfileCommand]):
    name = "SaveCompanyProfileUseCase"
