"""Save hardware config use case — single canonical route.

SIN COLABORADOR HOY. Su único `hardware_settings_service` posible era
`backend/application/services/hardware_settings_service.py`, eliminado por ser
una delegación a `core.repositories.hardware_config_repository` (borrado) sin
ningún consumidor en producción. Este caso de uso no se borró con él porque no
estaba en el alcance aprobado, pero tampoco es invocable: no queda nada que
pasarle.

Queda pendiente de una de dos decisiones, y conviene tomarla explícitamente en
vez de dejarlo así: reconstruir la escritura de configuración de hardware sobre
`hardware_config` dentro de `backend/infrastructure/` —cuando el panel de
Configuración → Dispositivos la necesite de verdad— o retirarlo.
"""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveHardwareConfigCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SaveHardwareConfigUseCase(BaseUseCase[SaveHardwareConfigCommand]):
    name = "SaveHardwareConfigUseCase"

    def __init__(self, hardware_settings_service) -> None:
        self._service = hardware_settings_service

    def execute(self, command: SaveHardwareConfigCommand) -> UseCaseResult:
        command.validate_context()
        self._service.save_one(command.device_type, dict(command.config))
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=command.device_type)
