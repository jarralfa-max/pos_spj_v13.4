"""Save SMTP settings use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveSMTPSettingsCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SaveSMTPSettingsUseCase(BaseUseCase[SaveSMTPSettingsCommand]):
    name = "SaveSMTPSettingsUseCase"

    def __init__(self, email_settings_service) -> None:
        self._service = email_settings_service

    def execute(self, command: SaveSMTPSettingsCommand) -> UseCaseResult:
        command.validate_context()
        self._service.save_settings(
            {
                "smtp_host": command.host,
                "smtp_port": str(command.port),
                "smtp_user": command.username,
                "smtp_password": command.password,
                "smtp_tls": "1" if command.use_tls else "0",
                "email_gerente": command.from_email,
            }
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id="smtp")
