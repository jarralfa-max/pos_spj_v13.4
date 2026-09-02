"""Set installation branch use case — single canonical route to anchor
THIS terminal to a branch (`configuraciones.sucursal_instalacion_id`,
read by `core/app_container.py`/`branch_resolution.py` at startup).
Wraps the already-correct, UoW-wrapped
`core/services/configuration_settings_service.py::CompanyProfileService
.set_installation_branch()`, which validates the branch exists and is
active before persisting."""

from __future__ import annotations

from backend.application.commands.settings_commands import SetInstallationBranchCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SetInstallationBranchUseCase(BaseUseCase[SetInstallationBranchCommand]):
    name = "SetInstallationBranchUseCase"

    def __init__(self, company_profile_service) -> None:
        self._service = company_profile_service

    def execute(self, command: SetInstallationBranchCommand) -> UseCaseResult:
        command.validate_context()
        branch_id, branch_name = self._service.set_installation_branch(command.branch_id)
        return UseCaseResult(
            success=True, operation_id=command.operation_id,
            entity_id=branch_id, data={"branch_name": branch_name},
        )
