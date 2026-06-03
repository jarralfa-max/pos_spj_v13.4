"""Small RRHH data shapes used by repository ports.

These dataclasses intentionally mirror the legacy SQLite tables instead of
introducing a new schema. They are safe DTOs for phase 1 and do not change the
current PyQt or service behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Employee:
    id: int
    nombre: str
    apellidos: str = ""
    puesto: str = ""
    salario: float = 0.0
    fecha_ingreso: str = ""
    activo: bool = True
    telefono: str = ""
    email: str = ""
    sucursal_id: Optional[int] = None

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellidos}".strip()


@dataclass(frozen=True)
class AttendanceRecord:
    id: int
    personal_id: int
    fecha: str
    hora_entrada: str = ""
    hora_salida: str = ""
    horas_trabajadas: float = 0.0
    estado: str = "PRESENTE"
    observaciones: str = ""


@dataclass(frozen=True)
class LeaveRequest:
    id: int
    personal_id: int
    tipo: str
    fecha_inicio: str
    fecha_fin: str
    dias: int = 1
    estado: str = "aprobado"
    notas: str = ""


@dataclass(frozen=True)
class PayrollRecord:
    id: int
    personal_id: int
    periodo_inicio: str
    periodo_fin: str
    salario_base: float = 0.0
    deducciones: float = 0.0
    bonos: float = 0.0
    neto_pagar: float = 0.0
    estado: str = "pendiente"
    aprobado_por: str = ""


@dataclass(frozen=True)
class PayrollPayment:
    id: int
    empleado_id: int
    periodo_inicio: str
    periodo_fin: str
    salario_base: float
    total: float
    metodo_pago: str = "efectivo"
    estado: str = "pagado"
    usuario: str = ""
    bonos: float = 0.0
    deducciones: float = 0.0
    fecha: str = ""


@dataclass(frozen=True)
class ShiftRole:
    id: int
    nombre: str
    hora_inicio: str = "08:00"
    hora_fin: str = "16:00"
    descripcion: str = ""
    color: str = "#3498db"
    activo: bool = True


@dataclass(frozen=True)
class ShiftAssignment:
    id: int
    personal_id: int
    turno_rol_id: int
    fecha_inicio: str
    fecha_fin: str = ""
    dia_descanso: str = "Domingo"
    rotacion_dias: int = 7
    notif_semana: bool = True
    notif_dia: bool = True
    activo: bool = True
    notas: str = ""
