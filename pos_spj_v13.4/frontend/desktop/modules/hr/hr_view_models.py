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
}

LEAVE_TYPE_ES = {
    "VACATION": "Vacaciones",
    "SICK_LEAVE": "Incapacidad",
    "PAID_LEAVE": "Permiso con goce",
    "UNPAID_LEAVE": "Permiso sin goce",
    "MATERNITY": "Maternidad",
    "PATERNITY": "Paternidad",
    "BEREAVEMENT": "Duelo",
    "OTHER": "Otro",
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
}


def status_es(value: str | None) -> str:
    return STATUS_ES.get(str(value or ""), str(value or ""))


def leave_type_es(value: str | None) -> str:
    return LEAVE_TYPE_ES.get(str(value or ""), str(value or ""))


def concept_es(value: str | None) -> str:
    return CONCEPT_ES.get(str(value or ""), str(value or ""))


def money_display(value) -> str:
    try:
        return f"${float(str(value)):,.2f}"
    except (TypeError, ValueError):
        return str(value or "")


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


@dataclass(frozen=True)
class KpiViewModel:
    title: str
    value: str
    variant: str = "primary"
