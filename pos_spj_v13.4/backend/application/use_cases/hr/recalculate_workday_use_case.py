"""Recalculate canonical HR attendance workdays from immutable punches."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.application.commands.attendance_commands import RecalculateWorkdayCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.domain.hr.entities import AttendanceWorkday
from backend.domain.hr.enums import WorkdayStatus
from backend.domain.hr.repository_ports import AttendanceRepositoryPort
from backend.domain.hr.services.workday_builder import WorkdayBuilder


class RecalculateWorkdayUseCase(BaseUseCase[RecalculateWorkdayCommand]):
    name = "RecalculateWorkdayUseCase"

    def __init__(self, attendance_repository: AttendanceRepositoryPort, *, builder: WorkdayBuilder | None = None) -> None:
        self._attendance_repository = attendance_repository
        self._builder = builder or WorkdayBuilder()

    def execute(self, command: RecalculateWorkdayCommand) -> UseCaseResult:
        command.validate_context()
        work_date = command.work_date
        if work_date is None:
            raise ValueError("work_date is required")
        current = self._attendance_repository.get_workday(
            employee_id=command.employee_id,
            branch_id=command.branch_id,
            work_date=work_date,
        )
        base = current or AttendanceWorkday(
            employee_id=command.employee_id,
            branch_id=command.branch_id,
            work_date=work_date,
            status=WorkdayStatus.ABSENT,
        )
        base.updated_at = datetime.now(UTC)
        punches = self._attendance_repository.list_punches_for_workday(
            employee_id=command.employee_id,
            branch_id=command.branch_id,
            work_date=work_date,
        )
        workday = self._builder.build(punches, base)
        self._attendance_repository.save_workday(workday)
        return UseCaseResult(
            success=True,
            operation_id=command.operation_id,
            entity_id=workday.id,
            message="Jornada recalculada correctamente.",
            data={"status": workday.status.value, "worked_minutes": workday.worked_minutes},
        )
