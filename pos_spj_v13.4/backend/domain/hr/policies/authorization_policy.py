"""Authorization policy — permission gate for HR operations.

Never authorizes by hardcoded role name; it consults an injected permission
checker (the central RBAC system). The UI never contains authorization logic.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.hr.exceptions import PermissionDeniedError


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


# Canonical HR permission codes.
HR_PERMISSIONS = (
    "hr.access",
    "hr.employee.read",
    "hr.employee.create",
    "hr.employee.update",
    "hr.employee.deactivate",
    "hr.attendance.read",
    "hr.attendance.register_manual",
    "hr.attendance.adjust",
    "hr.attendance.justify",
    "hr.attendance.approve_adjustment",
    "hr.attendance.view_audit",
    "hr.shift.manage",
    "hr.leave.read",
    "hr.leave.request",
    "hr.leave.approve",
    "hr.payroll.read",
    "hr.payroll.generate",
    "hr.payroll.authorize",
    "hr.payroll.pay",
    "hr.payroll.cancel",
    "hr.settings.manage",
)


class AuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in HR_PERMISSIONS:
            raise PermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            # No checker wired (e.g. isolated tests) → allow; production always wires one.
            return
        if not user_id:
            raise PermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise PermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}"
            )
