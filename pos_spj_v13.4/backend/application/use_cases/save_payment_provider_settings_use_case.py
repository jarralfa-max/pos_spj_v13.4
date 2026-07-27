"""Save payment provider settings use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import SavePaymentProviderSettingsCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SavePaymentProviderSettingsUseCase(BaseUseCase[SavePaymentProviderSettingsCommand]):
    name = "SavePaymentProviderSettingsUseCase"

    def __init__(self, payment_provider_settings_service) -> None:
        self._service = payment_provider_settings_service

    def execute(self, command: SavePaymentProviderSettingsCommand) -> UseCaseResult:
        command.validate_context()
        self._service.save_mercado_pago_settings(
            {
                "mp_access_token": command.access_token,
                "mp_webhook_url": command.webhook_url,
                "mp_return_url": command.return_url,
            }
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id="mercado_pago")
