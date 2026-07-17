"""Spanish (México) labels for status codes and common UI strings.

Single source so every module shows the same wording. Backend emits English
enum values; the UI maps them here.
"""

from __future__ import annotations

STATUS_ES = {
    # generic lifecycle
    "DRAFT": "Borrador",
    "PENDING": "Pendiente",
    "SUBMITTED": "Enviado",
    "VALIDATED": "Validado",
    "APPROVED": "Aprobado",
    "AUTHORIZED": "Autorizado",
    "REJECTED": "Rechazado",
    "CANCELLED": "Cancelado",
    "COMPLETED": "Completado",
    "ACTIVE": "Activo",
    "INACTIVE": "Inactivo",
    # finance
    "POSTED": "Contabilizado",
    "REVERSED": "Reversado",
    "OPEN": "Abierto",
    "SOFT_CLOSED": "Pre-cierre",
    "CLOSED": "Cerrado",
    "PARTIALLY_COLLECTED": "Cobro parcial",
    "SETTLED": "Liquidado",
    "WRITTEN_OFF": "Castigado",
    "SCHEDULED": "Programado",
    "PARTIALLY_PAID": "Pago parcial",
    "EXECUTED": "Ejecutado",
    "RECONCILED": "Conciliado",
    "PAID": "Pagada",
    # hr
    "ON_LEAVE": "Con permiso",
    "SUSPENDED": "Suspendido",
    "TERMINATED": "Baja",
    "COMPLETE": "Completa",
    "INCIDENT": "Incidencia",
    "ADJUSTED": "Ajustada",
    "CALCULATED": "Calculada",
    "UNDER_REVIEW": "En revisión",
}

# Reusable UI strings (buttons, actions, empty/loading/error states).
UI = {
    "action.save": "Guardar",
    "action.accept": "Aceptar",
    "action.cancel": "Cancelar",
    "action.close": "Cerrar",
    "action.delete": "Eliminar",
    "action.confirm": "Confirmar",
    "action.refresh": "Actualizar",
    "action.search": "Buscar",
    "action.export": "Exportar",
    "action.new": "Nuevo",
    "state.loading": "Cargando…",
    "state.empty": "Sin datos para mostrar",
    "state.error": "No fue posible cargar la información",
    "state.no_permission": "No tienes permiso para ver esta sección",
    "state.offline": "Sin conexión",
    "state.stale": "Información desactualizada",
    "state.partial": "Datos parciales",
    "select.placeholder": "Selecciona…",
}


def status_label(code: str | None) -> str:
    return STATUS_ES.get(str(code or ""), str(code or ""))


def ui(key: str) -> str:
    return UI.get(key, key)
