"""Save role permissions use case."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveRolePermissionsCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class SaveRolePermissionsUseCase(DelegatingUseCase[SaveRolePermissionsCommand]):
    name = "SaveRolePermissionsUseCase"
