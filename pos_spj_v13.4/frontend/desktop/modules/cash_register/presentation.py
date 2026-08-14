"""User-facing presentation helpers for Caja.

This file is intentionally UI-only. It translates technical identifiers,
domain enums and backend exceptions into operational Spanish without changing
the canonical domain model or persistence contracts.
"""

from __future__ import annotations

import re


UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


MOVEMENT_LABELS = {
    "OPENING_FLOAT": "Fondo inicial",
    "CASH_SALE": "Venta en efectivo",
    "CASH_REFUND": "Reembolso en efectivo",
    "CASH_IN": "Ingreso",
    "CASH_OUT": "Retiro",
    "MANUAL_INCOME": "Ingreso manual",
    "MANUAL_WITHDRAWAL": "Retiro",
    "SAFE_DROP": "Retiro a boveda",
    "CASH_PICKUP": "Recoleccion",
    "CASH_HANDOVER": "Entrega de valores",
    "CASH_RECEIPT": "Recepcion de valores",
    "CHANGE_ADDITION": "Cambio agregado",
    "AUTHORIZED_PAID_OUT": "Pago autorizado",
    "ADJUSTMENT": "Ajuste",
    "REVERSAL": "Reverso",
}

DIRECTION_LABELS = {
    "INFLOW": "Entrada",
    "OUTFLOW": "Salida",
}

STATUS_LABELS = {
    "OPENING": "Abriendo",
    "OPEN": "Abierto",
    "SUSPENDED": "Suspendido",
    "PENDING_COUNT": "Pendiente de arqueo",
    "COUNTING": "En conteo",
    "COUNTED": "Contado",
    "PENDING_REVIEW": "Pendiente de revision",
    "CLOSING": "En cierre",
    "CLOSED": "Cerrado",
    "FORCE_CLOSED": "Cierre forzado",
    "CANCELLED": "Cancelado",
    "ACTIVE": "Activo",
    "INACTIVE": "Inactivo",
    "MAINTENANCE": "En mantenimiento",
    "BLOCKED": "Bloqueado",
    "RETIRED": "Retirado",
    "CRITICAL": "Critica",
    "HIGH": "Alta",
    "MEDIUM": "Media",
    "LOW": "Baja",
    "RESOLVED": "Resuelta",
    "PENDING": "Pendiente",
    "UNDER_REVIEW": "En revision",
    "PREPARED": "Preparada",
    "DELIVERED": "Entregada",
    "READY": "Lista",
    "IN_TRANSIT": "En traslado",
    "RECEIVED": "Recibida",
    "DISPUTED": "En disputa",
    "LOCAL_ONLY": "Solo local",
    "PENDING_SYNC": "Pendiente de sincronizar",
    "SYNCED": "Sincronizado",
    "SYNC_ERROR": "Error de sincronizacion",
    "CONFLICT": "Conflicto",
    "ONLINE": "En linea",
    "OFFLINE": "Sin conexion",
    "SHORTAGE": "Faltante",
    "OVERAGE": "Sobrante",
    "WITHIN_TOLERANCE": "Dentro de tolerancia",
}

SCOPE_LABELS = {
    "SYSTEM": "Todo el sistema",
    "COMPANY": "Empresa",
    "BRANCH": "Sucursal",
    "REGISTER": "Caja",
    "USER": "Usuario",
}


def mask_technical_ids(text: object, *, replacement: str = "referencia tecnica") -> str:
    return UUID_RE.sub(replacement, str(text or ""))


def display_code(prefix: str, entity_id: str | None) -> str:
    """Return a stable visible code derived from an internal id without exposing it."""

    raw = str(entity_id or "").replace("-", "").upper()
    suffix = raw[-6:] if raw else "------"
    return f"{prefix}-{suffix}"


def movement_label(value: object) -> str:
    key = str(value or "").strip().upper()
    return MOVEMENT_LABELS.get(key, key.replace("_", " ").title() if key else "Movimiento")


def direction_label(value: object) -> str:
    key = str(value or "").strip().upper()
    return DIRECTION_LABELS.get(key, key.replace("_", " ").title() if key else "")


def status_label(value: object) -> str:
    key = str(value or "").strip().upper()
    return STATUS_LABELS.get(key, key.replace("_", " ").title() if key else "")


def scope_label(value: object) -> str:
    key = str(value or "").strip().upper()
    return SCOPE_LABELS.get(key, key.replace("_", " ").title() if key else "")


def origin_label(*, reference_id: str | None = None, sale_id: str | None = None) -> str:
    if sale_id:
        return f"Venta {display_code('VTA', sale_id)}"
    if reference_id:
        return f"Documento {display_code('DOC', reference_id)}"
    return "Sin documento origen"


def user_facing_error(error: object) -> str:
    message = str(error or "").strip()
    lowered = message.lower()
    if "uuid" in lowered or "id no valida" in lowered or "identidad no valida" in lowered:
        return "No fue posible localizar el registro seleccionado. Actualiza la pantalla e intentalo nuevamente."
    if "cajon" in lowered and ("contexto" in lowered or "configur" in lowered):
        return "Esta estacion no tiene un cajon de efectivo configurado."
    if "terminal" in lowered and ("contexto" in lowered or "configur" in lowered):
        return "Esta estacion no tiene una terminal configurada."
    if "dispositivo de sincronizacion" in lowered:
        return "Esta estacion no tiene sincronizacion local configurada."
    if "turno" in lowered and "abierto" in lowered:
        return "La operacion requiere un turno de caja abierto."
    if "permiso" in lowered or "autoriz" in lowered:
        return "No tienes permiso para completar esta operacion."
    return mask_technical_ids(message or "No fue posible completar la operacion.")
