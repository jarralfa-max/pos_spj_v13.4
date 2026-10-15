"""Controladores de checador (2026-10-14).

Un controlador SÓLO traduce el protocolo del fabricante a
``DeviceAttendanceEvent``; asistencia, nómina e idempotencia no cambian al
agregar un aparato nuevo. Para soportar otro modelo se escribe una clase con
``key``, ``fetch_events(device, cursor, *, tz)`` y ``probe(device)`` y se agrega a
``TIME_CLOCK_DRIVERS``.

* ``keyboard`` — lector USB que "teclea" la tarjeta/QR en el kiosco: no se
  descarga nada, cada lectura llega por ``KioskPunchUseCase``.
* ``attlog_file`` — archivo exportado por el checador (USB/memoria): formato
  ``attlog`` de ZKTeco (``usuario<TAB>AAAA-MM-DD HH:MM:SS<TAB>verificación<TAB>estado``)
  o CSV con encabezado ``usuario,fecha_hora[,estado]``. También sirve como
  descarga automática si ``connection["path"]`` apunta a la carpeta compartida
  donde el aparato deja su archivo.
* ``zkteco`` — checador ZKTeco por red (puerto 4370) con el paquete ``pyzk``.
  Si el paquete no está instalado, la sincronización lo dice claramente.
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime

from backend.domain.hr.time_clock import (
    CredentialType,
    DeviceAttendanceEvent,
    DeviceEventKind,
)

#: Estado ZKTeco: 0 = entrada, 1 = salida; 4/5 horas extra entrada/salida.
_ZK_STATUS = {"0": DeviceEventKind.CHECK_IN, "1": DeviceEventKind.CHECK_OUT,
              "4": DeviceEventKind.CHECK_IN, "5": DeviceEventKind.CHECK_OUT}


def _event_id(user: str, moment: str, status: str) -> str:
    """Identidad estable del evento: volver a importar el mismo renglón no duplica."""
    return hashlib.sha256(f"{user}|{moment}|{status}".encode("utf-8")).hexdigest()[:32]


def _moment(text: str, tz) -> datetime:
    value = datetime.fromisoformat(text.strip().replace("/", "-").replace("T", " "))
    return value.replace(tzinfo=tz) if value.tzinfo is None and tz is not None else value


def parse_attendance_file(path: str, *, tz=None, since: str | None = None):
    """Lee un archivo attlog/CSV y devuelve ``DeviceAttendanceEvent`` en orden."""
    with open(path, encoding="utf-8-sig", errors="replace") as handle:
        content = handle.read()
    return parse_attendance_text(content, tz=tz, since=since)


def parse_attendance_text(content: str, *, tz=None, since: str | None = None):
    events = []
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines:
        return events
    if "," in lines[0] and not lines[0].split(",")[0].strip().isdigit():
        reader = csv.DictReader(io.StringIO(content))
        rows = [((r.get("usuario") or r.get("user_id") or "").strip(),
                 (r.get("fecha_hora") or r.get("timestamp") or "").strip(),
                 (r.get("estado") or r.get("status") or "").strip()) for r in reader]
    else:
        rows = []
        for line in lines:
            parts = [part.strip() for part in line.split("\t")]
            if len(parts) < 2:
                raise ValueError(f"Renglón sin usuario y fecha: {line!r}")
            rows.append((parts[0], parts[1], parts[3] if len(parts) > 3 else ""))
    for user, stamp, status in rows:
        if not user or not stamp:
            continue
        if since and stamp <= since:
            continue
        events.append(DeviceAttendanceEvent(
            device_event_id=_event_id(user, stamp, status),
            credential_type=CredentialType.DEVICE_USER, raw_value=user,
            occurred_at=_moment(stamp, tz),
            kind=_ZK_STATUS.get(status, DeviceEventKind.UNSPECIFIED),
            verify_method="archivo"))
    return sorted(events, key=lambda event: event.occurred_at)


class KeyboardReaderDriver:
    key = "keyboard"

    def fetch_events(self, device, cursor, *, tz=None):
        return [], cursor

    def probe(self, device) -> tuple[bool, str]:
        return True, "Lector de kiosco: las lecturas llegan desde la pantalla Checador"


class AttLogFileDriver:
    key = "attlog_file"

    def fetch_events(self, device, cursor, *, tz=None):
        path = str((device.connection or {}).get("path") or "").strip()
        if not path:
            raise ValueError("El checador no tiene configurado el archivo (connection.path)")
        events = parse_attendance_file(path, tz=tz, since=cursor)
        newest = max((e.occurred_at.replace(tzinfo=None).isoformat(sep=" ") for e in events),
                     default=cursor)
        return events, newest

    def probe(self, device) -> tuple[bool, str]:
        import os
        path = str((device.connection or {}).get("path") or "")
        return (os.path.isfile(path), path or "sin archivo configurado")


class ZkTecoNetworkDriver:
    key = "zkteco"

    def _client(self, device):
        try:
            from zk import ZK  # paquete opcional ``pyzk``
        except ImportError as exc:
            raise RuntimeError("Para checadores ZKTeco por red instala el paquete «pyzk»") from exc
        settings = device.connection or {}
        host = str(settings.get("host") or "").strip()
        if not host:
            raise ValueError("El checador no tiene dirección IP (connection.host)")
        return ZK(host, port=int(settings.get("port") or 4370),
                  timeout=int(settings.get("timeout") or 5),
                  password=int(settings.get("password") or 0))

    def fetch_events(self, device, cursor, *, tz=None):
        client = self._client(device).connect()
        try:
            records = client.get_attendance() or []
        finally:
            client.disconnect()
        events = []
        newest = cursor
        for record in records:
            stamp = record.timestamp.isoformat(sep=" ")
            if cursor and stamp <= cursor:
                continue
            status = str(getattr(record, "punch", getattr(record, "status", "")))
            events.append(DeviceAttendanceEvent(
                device_event_id=_event_id(str(record.user_id), stamp, status),
                credential_type=CredentialType.DEVICE_USER, raw_value=str(record.user_id),
                occurred_at=record.timestamp.replace(tzinfo=tz) if tz else record.timestamp,
                kind=_ZK_STATUS.get(status, DeviceEventKind.UNSPECIFIED),
                verify_method=str(getattr(record, "status", ""))))
            newest = max(newest or stamp, stamp)
        return sorted(events, key=lambda e: e.occurred_at), newest

    def probe(self, device) -> tuple[bool, str]:
        try:
            client = self._client(device).connect()
            client.disconnect()
            return True, "Conectado"
        except Exception as exc:  # noqa: BLE001 - diagnóstico para el operador
            return False, str(exc)


TIME_CLOCK_DRIVERS = {driver.key: driver for driver in
                      (KeyboardReaderDriver(), AttLogFileDriver(), ZkTecoNetworkDriver())}
