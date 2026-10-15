"""Authorization policy — permission gate for HR operations.

Never authorizes by hardcoded role name; it consults an injected permission
checker (the central RBAC system). The UI never contains authorization logic.

Auditoría RRHH cebf67a HR-01: sin verificador la política PERMITÍA todo, y la
composición de producción nunca inyectaba uno — con una sesión sin permisos se
daba de alta un empleado. Ahora falla cerrada (sin verificador, sin usuario,
código desconocido o sin el permiso → se rechaza) y el vocabulario es el
estándar del ERP ``RRHH.<accion>`` registrado en el catálogo central.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.hr.exceptions import PermissionDeniedError


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class HRPermission:
    """Vocabulario ``RRHH.<accion>`` (MODULO.accion, como Compras/Finanzas)."""

    VIEW = "RRHH.ver"
    # Expediente
    EMPLOYEE_VIEW = "RRHH.empleado.ver"
    EMPLOYEE_CREATE = "RRHH.empleado.crear"
    EMPLOYEE_UPDATE = "RRHH.empleado.editar"
    EMPLOYEE_DEACTIVATE = "RRHH.empleado.baja"
    # Asistencia
    ATTENDANCE_VIEW = "RRHH.asistencia.ver"
    ATTENDANCE_MANUAL = "RRHH.asistencia.registrar_manual"
    ATTENDANCE_ADJUST = "RRHH.asistencia.solicitar_ajuste"
    ATTENDANCE_JUSTIFY = "RRHH.asistencia.justificar"
    ATTENDANCE_APPROVE_ADJUSTMENT = "RRHH.asistencia.aprobar_ajuste"
    ATTENDANCE_AUDIT = "RRHH.asistencia.ver_auditoria"
    # Turnos
    SHIFT_MANAGE = "RRHH.turno.gestionar"
    # Ausencias
    LEAVE_VIEW = "RRHH.permiso.ver"
    LEAVE_REQUEST = "RRHH.permiso.solicitar"
    LEAVE_APPROVE = "RRHH.permiso.aprobar"
    LEAVE_SELF_APPROVE = "RRHH.permiso.autoaprobar"
    LEAVE_CANCEL_APPROVED = "RRHH.permiso.cancelar_aprobado"
    # Nómina
    PAYROLL_VIEW = "RRHH.nomina.ver"
    PAYROLL_GENERATE = "RRHH.nomina.generar"
    PAYROLL_AUTHORIZE = "RRHH.nomina.autorizar"
    PAYROLL_PAY = "RRHH.nomina.pagar"
    PAYROLL_CANCEL = "RRHH.nomina.cancelar"
    PAYROLL_RECEIPT = "RRHH.nomina.recibo"
    PAYROLL_COMPLEMENTARY = "RRHH.nomina.complementaria"
    PAYROLL_REVERSE_PAYMENT = "RRHH.nomina.revertir_pago"
    # Percepciones y deducciones capturadas (bonos, comisiones, préstamos)
    PAYROLL_INPUT_CAPTURE = "RRHH.concepto.capturar"
    PAYROLL_INPUT_APPROVE = "RRHH.concepto.aprobar"
    LOAN_GRANT = "RRHH.prestamo.otorgar"
    # Saldo de vacaciones
    LEAVE_BALANCE_ADJUST = "RRHH.permiso.ajustar_saldo"
    # Checador (lector de huella/rostro/tarjeta/QR)
    TIME_CLOCK_MANAGE = "RRHH.checador.gestionar"
    TIME_CLOCK_PUNCH = "RRHH.checador.registrar"
    # Configuración del módulo
    SETTINGS_MANAGE = "RRHH.configuracion.gestionar"
    # Alcance por sucursal (HR-02): la activa siempre; estas amplían.
    VIEW_ASSIGNED_BRANCHES = "RRHH.ver.sucursales_asignadas"
    VIEW_ALL_BRANCHES = "RRHH.ver.todas_sucursales"


HR_PERMISSIONS = frozenset(
    value for name, value in vars(HRPermission).items()
    if not name.startswith("_") and isinstance(value, str))

#: Acciones de sólo lectura (lo que recibe un rol de consulta).
HR_READ_PERMISSIONS = frozenset({
    HRPermission.VIEW, HRPermission.EMPLOYEE_VIEW, HRPermission.ATTENDANCE_VIEW,
    HRPermission.LEAVE_VIEW, HRPermission.PAYROLL_VIEW,
})


class AuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        if self._checker is None or not user_id or permission_code not in HR_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(str(user_id), permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in HR_PERMISSIONS:
            raise PermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            raise PermissionDeniedError(
                "RRHH sin verificador de permisos configurado; autorización denegada")
        if not user_id or not str(user_id).strip():
            raise PermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(str(user_id), permission_code):
            raise PermissionDeniedError(
                f"No tienes permiso para esta acción ({permission_code}).")

    def require_branch(self, user_id: str, branch_id: str | None) -> None:
        """HR-02: el comando opera sobre la sucursal del DOCUMENTO (empleado,
        solicitud, corrida). Un verificador que no sabe de sucursales (dobles de
        prueba) no restringe; el de la sesión viva sí, y falla cerrado. Una
        corrida sin sucursal (todas) exige alcance sobre todas."""
        can_access = getattr(self._checker, "can_access_branch", None)
        if can_access is None:
            return
        if not can_access(str(user_id or ""), str(branch_id or "")):
            raise PermissionDeniedError(
                "El documento pertenece a una sucursal fuera de tu alcance de RRHH")

    def can_access_branch(self, user_id: str, branch_id: str | None) -> bool:
        try:
            self.require_branch(user_id, branch_id)
        except PermissionDeniedError:
            return False
        return True
