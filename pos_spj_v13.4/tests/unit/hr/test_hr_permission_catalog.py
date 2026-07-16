from __future__ import annotations

from core.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS, permission_code


def test_hr_permission_catalog_contains_required_actions() -> None:
    required = {
        "access",
        "employee.read",
        "employee.create",
        "employee.update",
        "employee.deactivate",
        "attendance.read",
        "attendance.register_manual",
        "attendance.adjust",
        "attendance.justify",
        "attendance.approve_adjustment",
        "attendance.view_audit",
        "shift.manage",
        "leave.read",
        "leave.request",
        "leave.approve",
        "payroll.read",
        "payroll.generate",
        "payroll.authorize",
        "payroll.pay",
        "payroll.cancel",
        "settings.manage",
    }
    assert required <= set(CANONICAL_MODULE_PERMISSIONS["RRHH"])
    assert permission_code("rrhh", "employee.create") == "RRHH.employee.create"
