"""Save happy hour rule use case."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveHappyHourRuleCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class SaveHappyHourRuleUseCase(DelegatingUseCase[SaveHappyHourRuleCommand]):
    name = "SaveHappyHourRuleUseCase"
