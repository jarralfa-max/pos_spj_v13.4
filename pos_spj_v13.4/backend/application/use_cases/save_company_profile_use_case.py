"""Save company profile use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveCompanyProfileCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SaveCompanyProfileUseCase(BaseUseCase[SaveCompanyProfileCommand]):
    name = "SaveCompanyProfileUseCase"

    def __init__(self, system_settings_service) -> None:
        self._service = system_settings_service

    def execute(self, command: SaveCompanyProfileCommand) -> UseCaseResult:
        command.validate_context()
        self._service.save_many(
            {
                "nombre_empresa": command.name,
                "razon_social": command.fiscal_name,
                "rfc": command.rfc,
                "direccion": command.address,
                "telefono_empresa": command.phone,
                "email_empresa": command.email,
                "logo_path": command.logo_path,
            }
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=command.branch_id)
