"""Canonical module permission catalog for SPJ POS.

This catalog is the source of truth for module visibility. UI navigation,
Configuración permission matrix and SessionContext checks must all use the same
`MODULO.accion` permission code format.
"""
from __future__ import annotations

CANONICAL_MODULE_PERMISSIONS: dict[str, list[str]] = {
    "DASHBOARD": ["ver"],
    "POS": ["ver", "crear", "cancelar", "descuento"],
    "CAJA": ["ver", "abrir", "cerrar", "retiro", "corte_z"],
    "INVENTARIO": ["ver", "ajustar", "transferir"],
    "TRANSFERENCIAS": ["ver", "crear", "recibir", "cancelar"],
    "PRODUCTOS": ["ver", "crear", "editar", "eliminar"],
    "CLIENTES": ["ver", "crear", "editar", "credito"],
    "MERMA": ["ver", "crear", "autorizar"],
    "DELIVERY": ["ver", "crear", "asignar", "entregar"],
    "COMPRAS": ["ver", "crear", "recibir"],
    "COTIZACIONES": ["ver", "crear", "aprobar", "convertir"],
    "PRODUCCION": ["ver", "ejecutar"],
    "ETIQUETAS": ["ver", "imprimir"],
    "PLANEACION_COMPRAS": ["ver", "generar"],
    "FINANZAS_UNIFICADAS": ["ver"],
    # Bounded context financiero (nuevo). Los permisos de instrumentos
    # comerciales siguen §24 del contrato: nunca autorizar por nombre de rol.
    "FINANZAS": [
        "ver",
        "asiento.crear",
        "asiento.reversar",
        "periodo.cerrar",
        "periodo.reabrir",
        "cxc.ver",
        "cobro.crear",
        "cxp.ver",
        "pago.programar",
        "pago.autorizar",
        "pago.ejecutar",
        "tesoreria.ver",
        "tesoreria.transferir",
        "conciliacion.ver",
        "conciliacion.ejecutar",
        "presupuesto.ver",
        "presupuesto.aprobar",
        "activo.ver",
        "activo.capitalizar",
        "estados.ver",
        "commercial_obligation.read",
        "commercial_obligation.reconcile",
        "commercial_posting_profile.read",
        "commercial_posting_profile.manage",
        "commercial_adjustment.create",
        "commercial_adjustment.authorize",
    ],
    "ACTIVOS": ["ver", "crear", "mantenimiento"],
    "RRHH": [
        "ver", "access",
        "employee.read", "employee.create", "employee.update", "employee.deactivate",
        "attendance.read", "attendance.register_manual", "attendance.adjust",
        "attendance.justify", "attendance.approve_adjustment", "attendance.view_audit",
        "shift.manage", "leave.read", "leave.request", "leave.approve",
        "payroll.read", "payroll.generate", "payroll.authorize", "payroll.pay",
        "payroll.cancel", "settings.manage",
    ],
    "GROWTH_ENGINE": ["ver"],
    "TARJETAS_FIDELIDAD": ["ver"],
    "INTELIGENCIA_BI": [
        "ver", "ver_ventas", "ver_inventario", "ver_compras", "ver_caja",
        "ver_clientes", "ver_proveedores", "ver_finanzas", "ver_merma",
        "exportar", "configurar",
    ],
    "WHATSAPP": ["ver"],
    "DISEÑADOR_TICKETS": ["ver"],
    "CONFIG_HARDWARE": ["ver"],
    "CONFIG_MODULOS": ["ver"],
    "CONFIG_SEGURIDAD": ["ver", "editar"],
}


def normalize_permission(code: str) -> str:
    """Normalize permission codes so comparisons are case-insensitive."""
    return str(code or "").strip().upper()


def permission_code(module: str, action: str) -> str:
    """Build a canonical permission code using `MODULE.action` format."""
    return f"{str(module or '').strip().upper()}.{str(action or '').strip().lower()}"


def module_view_permission(module: str) -> str:
    """Return the canonical module visibility permission."""
    return permission_code(module, "ver")
