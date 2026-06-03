"""Canonical RRHH event catalog and validated payloads.

All payload dataclasses require a non-empty ``operation_id`` so downstream
handlers can add idempotency in later phases without changing event contracts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Dict, Optional, Protocol
from uuid import uuid4

from core.events.event_bus import get_bus

# ── Canonical event names ────────────────────────────────────────────────────
EMPLEADO_CREADO = "EMPLEADO_CREADO"
EMPLEADO_ACTUALIZADO = "EMPLEADO_ACTUALIZADO"
EMPLEADO_DESACTIVADO = "EMPLEADO_DESACTIVADO"
EMPLEADO_ASIGNADO_SUCURSAL = "EMPLEADO_ASIGNADO_SUCURSAL"

ASISTENCIA_REGISTRADA = "ASISTENCIA_REGISTRADA"
RETARDO_REGISTRADO = "RETARDO_REGISTRADO"
FALTA_REGISTRADA = "FALTA_REGISTRADA"
HORAS_EXTRA_REGISTRADAS = "HORAS_EXTRA_REGISTRADAS"

VACACIONES_SOLICITADAS = "VACACIONES_SOLICITADAS"
VACACIONES_APROBADAS = "VACACIONES_APROBADAS"
VACACIONES_RECHAZADAS = "VACACIONES_RECHAZADAS"
PERMISO_SOLICITADO = "PERMISO_SOLICITADO"
PERMISO_APROBADO = "PERMISO_APROBADO"

NOMINA_GENERADA = "NOMINA_GENERADA"
NOMINA_AUTORIZADA = "NOMINA_AUTORIZADA"
NOMINA_PAGADA = "NOMINA_PAGADA"
NOMINA_CANCELADA = "NOMINA_CANCELADA"

ANTICIPO_NOMINA_SOLICITADO = "ANTICIPO_NOMINA_SOLICITADO"
ANTICIPO_NOMINA_APROBADO = "ANTICIPO_NOMINA_APROBADO"
ANTICIPO_NOMINA_PAGADO = "ANTICIPO_NOMINA_PAGADO"
ANTICIPO_NOMINA_DESCONTADO = "ANTICIPO_NOMINA_DESCONTADO"

COMISION_GENERADA = "COMISION_GENERADA"
COMISION_AUTORIZADA = "COMISION_AUTORIZADA"
COMISION_PAGADA = "COMISION_PAGADA"

REPARTIDOR_ASIGNADO = "REPARTIDOR_ASIGNADO"
ENTREGA_COMPLETADA_POR_REPARTIDOR = "ENTREGA_COMPLETADA_POR_REPARTIDOR"
PAGO_REPARTIDOR_GENERADO = "PAGO_REPARTIDOR_GENERADO"


def new_operation_id(prefix: str = "rrhh") -> str:
    """Create a non-empty idempotency key for RRHH application events."""
    return f"{prefix}-{uuid4().hex}"


class RRHHEventPayload(Protocol):
    event_type: ClassVar[str]
    operation_id: str

    def to_dict(self) -> Dict[str, Any]: ...


def _ensure_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} debe ser un entero positivo")


def _ensure_text(value: str, field_name: str) -> None:
    if not str(value or "").strip():
        raise ValueError(f"{field_name} es obligatorio")


@dataclass(frozen=True)
class _PayloadBase:
    operation_id: str

    def __post_init__(self) -> None:
        if not str(self.operation_id or "").strip():
            raise ValueError("operation_id es obligatorio para eventos RRHH")

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["event_type"] = self.event_type
        return payload


@dataclass(frozen=True)
class EmployeeEventPayload(_PayloadBase):
    event_type: ClassVar[str] = EMPLEADO_ACTUALIZADO
    employee_id: int
    nombre: str = ""
    puesto: str = ""
    sucursal_id: Optional[int] = None
    usuario: str = ""
    reason: str = ""
    changes: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        _ensure_positive_int(self.employee_id, "employee_id")


@dataclass(frozen=True)
class EmployeeCreatedPayload(EmployeeEventPayload):
    event_type: ClassVar[str] = EMPLEADO_CREADO


@dataclass(frozen=True)
class EmployeeDeactivatedPayload(EmployeeEventPayload):
    event_type: ClassVar[str] = EMPLEADO_DESACTIVADO


@dataclass(frozen=True)
class DriverAssignedPayload(_PayloadBase):
    event_type: ClassVar[str] = REPARTIDOR_ASIGNADO
    driver_id: int
    employee_id: int
    source_module: str = "rrhh"
    reason: str = "identity_link"

    def __post_init__(self) -> None:
        super().__post_init__()
        _ensure_positive_int(self.driver_id, "driver_id")
        _ensure_positive_int(self.employee_id, "employee_id")
        _ensure_text(self.source_module, "source_module")


@dataclass(frozen=True)
class AttendanceEventPayload(_PayloadBase):
    event_type: ClassVar[str] = ASISTENCIA_REGISTRADA
    attendance_id: int
    employee_id: int
    fecha: str
    tipo: str
    hora: str
    hours: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        _ensure_positive_int(self.attendance_id, "attendance_id")
        _ensure_positive_int(self.employee_id, "employee_id")
        _ensure_text(self.fecha, "fecha")
        _ensure_text(self.tipo, "tipo")
        _ensure_text(self.hora, "hora")
        if self.hours < 0:
            raise ValueError("hours no puede ser negativo")


@dataclass(frozen=True)
class LeaveEventPayload(_PayloadBase):
    event_type: ClassVar[str] = VACACIONES_SOLICITADAS
    request_id: int
    employee_id: int
    tipo: str
    date_start: str
    date_end: str
    days: int
    status: str

    def __post_init__(self) -> None:
        super().__post_init__()
        _ensure_positive_int(self.request_id, "request_id")
        _ensure_positive_int(self.employee_id, "employee_id")
        _ensure_text(self.tipo, "tipo")
        _ensure_text(self.date_start, "date_start")
        _ensure_text(self.date_end, "date_end")
        _ensure_text(self.status, "status")
        if self.days < 0:
            raise ValueError("days no puede ser negativo")


@dataclass(frozen=True)
class LeaveApprovedPayload(LeaveEventPayload):
    event_type: ClassVar[str] = VACACIONES_APROBADAS


@dataclass(frozen=True)
class LeaveRejectedPayload(LeaveEventPayload):
    event_type: ClassVar[str] = VACACIONES_RECHAZADAS


@dataclass(frozen=True)
class PermissionRequestedPayload(LeaveEventPayload):
    event_type: ClassVar[str] = PERMISO_SOLICITADO


@dataclass(frozen=True)
class PermissionApprovedPayload(LeaveEventPayload):
    event_type: ClassVar[str] = PERMISO_APROBADO


@dataclass(frozen=True)
class PayrollGeneratedPayload(_PayloadBase):
    event_type: ClassVar[str] = NOMINA_GENERADA
    employee_id: int
    period_start: str
    period_end: str
    total: float
    neto: float
    sucursal_id: int
    nombre: str = ""
    payroll_payment_id: Optional[int] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        _ensure_positive_int(self.employee_id, "employee_id")
        _ensure_text(self.period_start, "period_start")
        _ensure_text(self.period_end, "period_end")
        _ensure_positive_int(self.sucursal_id, "sucursal_id")
        if self.payroll_payment_id is not None:
            _ensure_positive_int(self.payroll_payment_id, "payroll_payment_id")
        if self.total < 0 or self.neto < 0:
            raise ValueError("total/neto no pueden ser negativos")


@dataclass(frozen=True)
class PayrollPaidPayload(_PayloadBase):
    event_type: ClassVar[str] = NOMINA_PAGADA
    payroll_payment_id: int
    employee_id: int
    period_start: str
    period_end: str
    total: float
    neto: float
    metodo_pago: str
    sucursal_id: int
    nombre: str = ""
    source_module: str = "rrhh"
    source_id: Optional[int] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        _ensure_positive_int(self.payroll_payment_id, "payroll_payment_id")
        _ensure_positive_int(self.employee_id, "employee_id")
        _ensure_text(self.period_start, "period_start")
        _ensure_text(self.period_end, "period_end")
        _ensure_text(self.metodo_pago, "metodo_pago")
        _ensure_positive_int(self.sucursal_id, "sucursal_id")
        if self.source_id is not None:
            _ensure_positive_int(self.source_id, "source_id")
        if self.total < 0 or self.neto < 0:
            raise ValueError("total/neto no pueden ser negativos")


class RRHHEventPublisher:
    """Publishes validated RRHH dataclass payloads through the project EventBus."""

    def __init__(self, bus: Any = None):
        self._bus = bus or get_bus()

    def publish(self, payload: RRHHEventPayload, *, async_: bool = False) -> None:
        # Calling to_dict validates operation_id via dataclass construction and
        # attaches the canonical event_type for downstream handlers.
        self._bus.publish(payload.event_type, payload.to_dict(), async_=async_)


__all__ = [
    "EMPLEADO_CREADO", "EMPLEADO_ACTUALIZADO", "EMPLEADO_DESACTIVADO",
    "EMPLEADO_ASIGNADO_SUCURSAL", "ASISTENCIA_REGISTRADA",
    "RETARDO_REGISTRADO", "FALTA_REGISTRADA", "HORAS_EXTRA_REGISTRADAS",
    "VACACIONES_SOLICITADAS", "VACACIONES_APROBADAS", "VACACIONES_RECHAZADAS",
    "PERMISO_SOLICITADO", "PERMISO_APROBADO", "NOMINA_GENERADA",
    "NOMINA_AUTORIZADA", "NOMINA_PAGADA", "NOMINA_CANCELADA",
    "ANTICIPO_NOMINA_SOLICITADO", "ANTICIPO_NOMINA_APROBADO",
    "ANTICIPO_NOMINA_PAGADO", "ANTICIPO_NOMINA_DESCONTADO",
    "COMISION_GENERADA", "COMISION_AUTORIZADA", "COMISION_PAGADA",
    "REPARTIDOR_ASIGNADO", "ENTREGA_COMPLETADA_POR_REPARTIDOR",
    "PAGO_REPARTIDOR_GENERADO", "AttendanceEventPayload",
    "DriverAssignedPayload", "EmployeeCreatedPayload", "EmployeeDeactivatedPayload",
    "EmployeeEventPayload", "LeaveApprovedPayload", "LeaveEventPayload",
    "LeaveRejectedPayload", "PayrollGeneratedPayload", "PayrollPaidPayload",
    "PermissionApprovedPayload", "PermissionRequestedPayload",
    "RRHHEventPublisher", "new_operation_id",
]
