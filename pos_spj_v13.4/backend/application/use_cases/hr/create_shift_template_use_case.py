"""Create reusable HR shift templates."""

from __future__ import annotations

from backend.application.commands.hr_commands import CreateShiftTemplateCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import ShiftTemplate
from backend.domain.hr.repository_ports import WorkShiftRepositoryPort


class CreateShiftTemplateUseCase(BaseUseCase[CreateShiftTemplateCommand]):
    name = "CreateShiftTemplateUseCase"

    def __init__(self, work_shift_repository: WorkShiftRepositoryPort, *, permission_checker: PermissionChecker | None = None) -> None:
        self._repository = work_shift_repository
        self._authorizer = HRPermissionAuthorizer(permission_checker)

    def execute(self, command: CreateShiftTemplateCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.shift.manage")
        template = ShiftTemplate(name=command.name.strip(), branch_id=command.branch_id, weekdays=command.weekdays, work_shift_id=command.work_shift_id)
        self._repository.save_template(template)
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=template.id)
