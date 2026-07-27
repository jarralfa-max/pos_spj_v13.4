"""Create employee rest days for HR scheduling."""

from __future__ import annotations

from backend.application.commands.hr_commands import CreateRestDayCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import RestDay
from backend.domain.hr.repository_ports import WorkShiftRepositoryPort


class CreateRestDayUseCase(BaseUseCase[CreateRestDayCommand]):
    name = "CreateRestDayUseCase"

    def __init__(self, work_shift_repository: WorkShiftRepositoryPort, *, permission_checker: PermissionChecker | None = None) -> None:
        self._repository = work_shift_repository
        self._authorizer = HRPermissionAuthorizer(permission_checker)

    def execute(self, command: CreateRestDayCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.shift.manage")
        rest_day = RestDay(employee_id=command.employee_id, branch_id=command.branch_id, rest_date=command.rest_date, reason=command.reason.strip())
        self._repository.save_rest_day(rest_day)
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=rest_day.id)
