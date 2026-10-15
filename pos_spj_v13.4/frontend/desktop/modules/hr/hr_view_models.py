"""View models for the HR module — display-ready strings only."""

from __future__ import annotations

from dataclasses import dataclass, field

STATUS_ES = {
    # employment
    "ACTIVE": "Activo",
    "INACTIVE": "Inactivo",
    "ON_LEAVE": "Con permiso",
    "SUSPENDED": "Suspendido",
    "TERMINATED": "Baja",
    # workday
    "OPEN": "Abierta",
    "COMPLETE": "Completa",
    "INCIDENT": "Incidencia",
    "ADJUSTED": "Ajustada",
    # adjustments / leave
    "PENDING": "Pendiente",
    "APPROVED": "Aprobado",
    "REJECTED": "Rechazado",
    "CANCELLED": "Cancelado",
    # payroll
    "DRAFT": "Borrador",
    "CALCULATED": "Calculada",
    "UNDER_REVIEW": "En revisión",
    "AUTHORIZED": "Autorizada",
    "PAID": "Pagada",
    "APPLIED": "Aplicado",
}
STATUS_ES.setdefault("ORDINARY", "Ordinaria")

LEAVE_TYPE_ES = {
    "VACATION": "Vacaciones",
    "SICK_LEAVE": "Incapacidad",
    "PAID_LEAVE": "Permiso con goce",
    "UNPAID_LEAVE": "Permiso sin goce",
    "MATERNITY": "Maternidad",
    "PATERNITY": "Paternidad",
    "BEREAVEMENT": "Duelo",
    "OTHER": "Otro",
    "ABSENCE_JUSTIFICATION": "Falta justificada",
}

CONCEPT_ES = {
    "BASE_SALARY": "Sueldo base",
    "OVERTIME": "Horas extra",
    "BONUS": "Bono",
    "COMMISSION": "Comisión",
    "ABSENCE_DEDUCTION": "Deducción por falta",
    "LATE_DEDUCTION": "Deducción por retardo",
    "TAX_WITHHOLDING": "Retención ISR",
    "SOCIAL_SECURITY": "Seguridad social",
    "LOAN_DEDUCTION": "Deducción por préstamo",
    "OTHER_DEDUCTION": "Otra deducción",
    "VACATION": "Vacaciones",
    "PAID_LEAVE": "Permiso con goce",
    "ADVANCE_DEDUCTION": "Deducción por anticipo",
    "ADJUSTMENT": "Ajuste",
}


TIME_CLOCK_KIND_ES = {
    "KEYBOARD_READER": "Lector USB (kiosco)", "FINGERPRINT": "Huella",
    "FACE_RECOGNITION": "Rostro", "RFID": "Tarjeta RFID", "QR": "Código QR",
    "MULTI": "Varios métodos",
}
TIME_CLOCK_DRIVER_ES = {
    "keyboard": "Kiosco (lector tipo teclado)", "attlog_file": "Archivo exportado",
    "zkteco": "ZKTeco por red",
}
CREDENTIAL_ES = {
    "DEVICE_USER": "Usuario del checador", "CARD": "Tarjeta", "QR": "QR", "PIN": "PIN",
}


def status_es(value: str | None) -> str:
    return STATUS_ES.get(str(value or ""), str(value or ""))


def leave_type_es(value: str | None) -> str:
    return LEAVE_TYPE_ES.get(str(value or ""), str(value or ""))


def concept_es(value: str | None) -> str:
    return CONCEPT_ES.get(str(value or ""), str(value or ""))


def money_display(value) -> str:
    """Formato de pantalla desde Decimal (HR-25: nunca ``float``)."""
    from decimal import Decimal, InvalidOperation
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return str(value or "")
    return f"${amount:,.2f}"


def local_clock(value, tz=None) -> str:
    """HH:MM en la zona de la sucursal de un instante guardado en UTC (HR-22:
    antes se recortaba el texto UTC y una entrada de 09:00 se veía 15:00)."""
    from datetime import datetime
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)[11:16] or "—"
    if moment.tzinfo is not None and tz is not None:
        moment = moment.astimezone(tz)
    return moment.strftime("%H:%M")


def minutes_display(value) -> str:
    try:
        minutes = int(value or 0)
    except (TypeError, ValueError):
        return str(value or "0")
    if minutes <= 0:
        return "—"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h {rest:02d}m" if hours else f"{rest}m"


def bool_display(value) -> str:
    return "Sí" if value else "No"


@dataclass(frozen=True)
class TableViewModel:
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)
    #: Total de filas que cumplen el filtro (para paginar); None = len(rows).
    total: int | None = None


@dataclass(frozen=True)
class KpiViewModel:
    title: str
    value: str
    variant: str = "primary"
