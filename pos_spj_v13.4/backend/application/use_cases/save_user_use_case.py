"""Save user use case."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveUserCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class SaveUserUseCase(DelegatingUseCase[SaveUserCommand]):
    name = "SaveUserUseCase"
