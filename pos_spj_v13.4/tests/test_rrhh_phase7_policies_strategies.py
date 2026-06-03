from datetime import date, datetime

import pytest

from core.rrhh.domain import (
    AttendanceHoursPolicy,
    AttendanceJustificationPolicy,
    Employee,
    EmployeeEligibilityPolicy,
    FixedAmountStrategy,
    HourlyPayStrategy,
    LeaveRequest,
    PayrollConceptCalculator,
    PayrollPeriodPolicy,
    PercentageStrategy,
    RestDayPolicy,
    VacationOverlapPolicy,
)


def _leave(leave_id, tipo, start, end, estado="aprobado"):
    return LeaveRequest(
        id=leave_id,
        personal_id=1,
        tipo=tipo,
        fecha_inicio=start,
        fecha_fin=end,
        dias=1,
        estado=estado,
    )


def test_phase7_policies_are_deterministic_and_cover_payroll_rules():
    assert AttendanceHoursPolicy().rounded_worked_hours("22:00", "02:30") == 4.5
    assert PayrollPeriodPolicy(period_days=7).current_period_strings(
        datetime(2026, 6, 3, 9, 0)
    ) == ("2026-05-27", "2026-06-03")

    active = Employee(id=1, nombre="Ana", apellidos="", activo=True)
    inactive = Employee(id=2, nombre="Luis", apellidos="", activo=False)
    assert EmployeeEligibilityPolicy().filter_payroll_eligible([active, inactive]) == [active]

    rest_policy = RestDayPolicy(max_consecutive_days=6, min_coverage=2)
    assert rest_policy.requires_rest(6) is True
    assert rest_policy.has_minimum_coverage(active_count=3, resting_today=1) is True
    assert rest_policy.has_minimum_coverage(active_count=2, resting_today=1) is False


def test_phase7_payroll_concept_strategies_are_composable():
    calculator = PayrollConceptCalculator(
        strategies=(
            HourlyPayStrategy(code="base_horas", hourly_rate=50.0),
            PercentageStrategy(code="bono", percent=0.10),
            FixedAmountStrategy(code="deduccion", amount=-25.0),
        )
    )

    assert HourlyPayStrategy(code="extra", hourly_rate=75).calculate(hours=2.5) == 187.5
    assert PercentageStrategy(code="isr", percent=-0.08).calculate(base_amount=1000) == -80.0
    assert FixedAmountStrategy(code="bono_fijo", amount=125.239).calculate() == 125.24
    assert calculator.calculate_total(base_amount=1000.0, hours=8.0) == 475.0


def test_phase7_vacation_overlap_blocks_active_requests_only():
    policy = VacationOverlapPolicy()
    overlaps = [
        _leave(1, "vacaciones", "2026-06-10", "2026-06-12", "rechazado"),
        _leave(2, "permiso", "2026-06-11", "2026-06-11", "pendiente"),
    ]

    with pytest.raises(ValueError, match="se solapa"):
        policy.ensure_no_overlap(overlaps, "aprobado")

    policy.ensure_no_overlap(overlaps, "rechazado")


def test_phase7_absence_discount_respects_vacation_permission_and_rest_day():
    policy = AttendanceJustificationPolicy()
    absence_date = date(2026, 6, 11)
    leaves = [
        _leave(1, "vacaciones", "2026-06-10", "2026-06-12", "aprobado"),
        _leave(2, "permiso", "2026-06-20", "2026-06-20", "pendiente"),
    ]

    assert policy.should_discount_absence(absence_date, leaves=leaves) is False
    assert policy.should_discount_absence(date(2026, 6, 20), leaves=leaves) is False
    assert policy.should_discount_absence(date(2026, 6, 15), rest_dates=[date(2026, 6, 15)]) is False
    assert policy.should_discount_absence(date(2026, 6, 16), leaves=leaves) is True
