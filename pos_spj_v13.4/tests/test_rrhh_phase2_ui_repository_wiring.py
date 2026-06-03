from pathlib import Path


RRHH_SRC = Path(__file__).resolve().parents[1] / "modulos" / "rrhh.py"


def _src() -> str:
    return RRHH_SRC.read_text(encoding="utf-8")


def test_rrhh_ui_imports_phase4_application_services_policies_and_sqlite_adapters():
    src = _src()
    assert "EmployeeApplicationService" in src
    assert "AttendanceApplicationService" in src
    assert "LeaveApplicationService" in src
    assert "PayrollPeriodPolicy" in src
    assert "SQLiteEmployeeRepository" in src
    assert "SQLiteAttendanceRepository" in src
    assert "SQLiteLeaveRepository" in src


def test_rrhh_employee_screen_uses_application_service_for_legacy_crud_paths():
    src = _src()
    assert "self.employee_service.get_employee" in src
    assert "self.employee_service.save_employee" in src
    assert "self.employee_service.list_active_employees" in src
    assert "self.employee_service.deactivate_employee" in src


def test_rrhh_payroll_uses_policy_and_employee_eligibility_service():
    src = _src()
    assert "self.payroll_period_policy.current_period_strings" in src
    assert "self.employee_service.list_payroll_eligible_employees" in src
    assert "datetime.now()" not in src[src.index("def ejecutar_calculo_nomina"):src.index("def aprobar_y_pagar")]


def test_rrhh_attendance_and_leave_screens_use_application_services_for_phase4_paths():
    src = _src()
    assert "self.attendance_service.list_attendance_table_rows" in src
    assert "self.attendance_service.get_status_for_date" in src
    assert "self.attendance_service.register_check_in_out" in src
    assert "self.leave_service.list_leave_table_rows" in src
    assert "self.leave_service.create_leave" in src


def test_rrhh_ui_does_not_publish_rrhh_events_directly_in_phase5():
    src = _src()
    assert "get_bus" not in src
    assert ".publish(" not in src
    assert "self.attendance_service.register_check_in_out" in src
    assert "self.leave_service.create_leave" in src
