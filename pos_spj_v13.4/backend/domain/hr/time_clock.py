"""Checador (lector de huella, rostro, tarjeta RFID, QR o PIN) — dominio.

Arquitectura (2026-10-14) para conectar hoy un lector USB tipo teclado y mañana
un checador de red (ZKTeco, Hikvision, Anviz…) SIN tocar asistencia ni nómina:

* ``TimeClockDevice`` — el aparato, por sucursal, con su tipo y conexión.
* ``EmployeeCredential`` — cómo el aparato identifica al empleado: el número de
  usuario del checador, la tarjeta, el QR o un PIN (guardado sólo como hash).
  **Las plantillas biométricas NO entran al ERP**: viven en el aparato; aquí sólo
  la referencia que el aparato reporta (protección de datos personales).
* ``DeviceAttendanceEvent`` — una marcación tal como la reporta el aparato. Se
  guarda SIEMPRE (evidencia, idempotencia por ``device_event_id``) y se convierte
  en marcación canónica por la misma ruta que caja y registro manual.
* El controlador concreto (``TimeClockDriver``, en infraestructura) sólo traduce
  el protocolo del fabricante a ``DeviceAttendanceEvent``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from backend.domain.hr.enums import AttendanceSource, PunchType
from backend.domain.hr.exceptions import HRDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TimeClockKind(str, Enum):
    KEYBOARD_READER = "KEYBOARD_READER"     # lector USB que "teclea" tarjeta/QR (kiosco)
    FINGERPRINT = "FINGERPRINT"
    FACE_RECOGNITION = "FACE_RECOGNITION"
    RFID = "RFID"
    QR = "QR"
    MULTI = "MULTI"                         # checador con varios métodos


class CredentialType(str, Enum):
    DEVICE_USER = "DEVICE_USER"   # número de usuario dado de alta en el checador
    CARD = "CARD"                 # tarjeta RFID/proximidad
    QR = "QR"
    PIN = "PIN"                   # se guarda como hash, nunca en claro


class DeviceEventKind(str, Enum):
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"
    UNSPECIFIED = "UNSPECIFIED"   # el aparato sólo dice "verificado": se alterna


class DeviceEventStatus(str, Enum):
    APPLIED = "APPLIED"
    DUPLICATE = "DUPLICATE"
    UNMATCHED = "UNMATCHED"       # credencial sin empleado: se reprocesa al enrolar
    REJECTED = "REJECTED"


#: Fuente de la marcación canónica según el tipo de aparato.
SOURCE_BY_KIND = {
    TimeClockKind.KEYBOARD_READER: AttendanceSource.TIME_CLOCK,
    TimeClockKind.FINGERPRINT: AttendanceSource.FINGERPRINT,
    TimeClockKind.FACE_RECOGNITION: AttendanceSource.FACE_RECOGNITION,
    TimeClockKind.RFID: AttendanceSource.RFID,
    TimeClockKind.QR: AttendanceSource.QR,
    TimeClockKind.MULTI: AttendanceSource.TIME_CLOCK,
}


def hash_secret(value: str) -> str:
    return hashlib.sha256(f"spj-hr-pin|{value}".encode("utf-8")).hexdigest()


def credential_key(credential_type: CredentialType, raw_value: str) -> str:
    """Valor con el que se busca la credencial. El PIN se compara por hash."""
    text = str(raw_value or "").strip()
    if not text:
        raise HRDomainError("La credencial está vacía")
    return hash_secret(text) if credential_type is CredentialType.PIN else text.upper()


@dataclass(slots=True)
class TimeClockDevice:
    id: str
    branch_id: str
    code: str
    name: str
    kind: TimeClockKind
    driver: str = "keyboard"              # clave del controlador registrado
    connection: dict = field(default_factory=dict)   # host/puerto/archivo… según controlador
    active: bool = True
    sync_cursor: str | None = None
    last_synced_at: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, branch_id: str, code: str, name: str, kind: TimeClockKind, *,
               driver: str = "keyboard", connection: dict | None = None) -> "TimeClockDevice":
        if not branch_id:
            raise HRDomainError("El checador requiere sucursal")
        if not str(code or "").strip() or not str(name or "").strip():
            raise HRDomainError("El checador requiere código y nombre")
        return cls(id=new_uuid(), branch_id=branch_id, code=code.strip().upper(),
                   name=name.strip(), kind=kind, driver=driver.strip() or "keyboard",
                   connection=dict(connection or {}))

    @property
    def source(self) -> AttendanceSource:
        return SOURCE_BY_KIND[self.kind]


@dataclass(slots=True)
class EmployeeCredential:
    id: str
    employee_id: str
    credential_type: CredentialType
    lookup_key: str
    device_id: str | None = None          # None = válida en cualquier checador
    label: str = ""                       # p. ej. últimos dígitos de la tarjeta
    active: bool = True
    enrolled_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def enroll(cls, employee_id: str, credential_type: CredentialType, raw_value: str, *,
               device_id: str | None = None, enrolled_by_user_id: str | None = None
               ) -> "EmployeeCredential":
        if not employee_id:
            raise HRDomainError("La credencial requiere empleado")
        key = credential_key(credential_type, raw_value)
        if credential_type is CredentialType.PIN and len(str(raw_value).strip()) < 4:
            raise HRDomainError("El PIN debe tener al menos 4 dígitos")
        visible = ("PIN" if credential_type is CredentialType.PIN
                   else f"…{str(raw_value).strip()[-4:]}")
        return cls(id=new_uuid(), employee_id=employee_id, credential_type=credential_type,
                   lookup_key=key, device_id=device_id, label=visible,
                   enrolled_by_user_id=enrolled_by_user_id)


@dataclass(frozen=True, slots=True)
class DeviceAttendanceEvent:
    """Marcación tal como la reporta el aparato (antes de saber de quién es)."""

    device_event_id: str
    credential_type: CredentialType
    raw_value: str
    occurred_at: datetime
    kind: DeviceEventKind = DeviceEventKind.UNSPECIFIED
    verify_method: str = ""

    def __post_init__(self) -> None:
        if not str(self.device_event_id or "").strip():
            raise HRDomainError("El evento del checador requiere su identificador")
        if not str(self.raw_value or "").strip():
            raise HRDomainError("El evento del checador no identifica a nadie")

    def punch_type(self, *, has_open_entry: bool) -> PunchType:
        if self.kind is DeviceEventKind.CHECK_IN:
            return PunchType.ENTRY
        if self.kind is DeviceEventKind.CHECK_OUT:
            return PunchType.EXIT
        return PunchType.EXIT if has_open_entry else PunchType.ENTRY
