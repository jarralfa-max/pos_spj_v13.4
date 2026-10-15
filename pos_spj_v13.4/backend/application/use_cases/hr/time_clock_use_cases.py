"""Checador — casos de uso (2026-10-14).

Una sola ruta convierte lo que reporta cualquier aparato en marcación canónica
(``IngestDeviceEventsUseCase`` → ``RegisterAttendancePunchUseCase``), así que el
checador hereda TODAS las reglas de asistencia: zona de la sucursal, turno
nocturno, segmentos, incidencias, idempotencia. Cada evento:

* se guarda siempre como evidencia (``hr_device_events``) y una vez:
  ``(aparato, id del evento)`` es único — reintentar una descarga no duplica;
* si la credencial no tiene empleado queda ``UNMATCHED`` y se aplica al enrolarla;
* entrada/salida: la que diga el aparato; si sólo dice "verificado", se alterna
  según haya o no una entrada abierta.

Modos: kiosco con lector USB tipo teclado (``KioskPunchUseCase``), descarga de
un checador de red (``SyncTimeClockDeviceUseCase`` con su controlador) e
importación del archivo que exporta el aparato (``ImportTimeClockFileUseCase``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.application.use_cases.hr.attendance_use_cases import (
    RegisterAttendancePunchUseCase,
)
from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission
from backend.domain.hr.time_clock import (
    CredentialType,
    DeviceAttendanceEvent,
    DeviceEventKind,
    DeviceEventStatus,
    EmployeeCredential,
    TimeClockDevice,
    TimeClockKind,
    credential_key,
)
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.business_dates import resolve_timezone
from backend.shared.ids import derived_uuidv7, new_uuid

#: Dos lecturas de la misma persona en menos de esto son un doble escaneo.
DUPLICATE_SCAN_SECONDS = 60


class RegisterTimeClockDeviceUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, branch_id: str, code: str, name: str,
                kind: str, driver: str = "keyboard", connection_settings: dict | None = None
                ) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.TIME_CLOCK_MANAGE)
        self._auth.require_branch(actor_user_id, branch_id)
        try:
            device = TimeClockDevice.create(branch_id, code, name, TimeClockKind(kind),
                                            driver=driver, connection=connection_settings)
        except (HRDomainError, ValueError) as exc:
            return HRResult.fail(str(exc), "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            if uow.time_clock.get_device_by_code(device.code):
                return HRResult.fail(f"Ya existe un checador con código {device.code}",
                                     "DUPLICATE_CODE")
            uow.time_clock.save_device(device)
            uow.audit.record(action="TIME_CLOCK_REGISTERED", actor_user_id=actor_user_id,
                             entity_type="time_clock", entity_id=device.id,
                             detail=f"{device.code} {device.kind.value} {device.driver}")
        return HRResult.ok("Checador registrado", entity_id=device.id)


class IngestDeviceEventsUseCase:
    """Convierte eventos de UN aparato en marcaciones (cada uno en su propia
    transacción: un evento malo no se lleva a los demás)."""

    def __init__(self) -> None:
        self._register = RegisterAttendancePunchUseCase()

    def execute(self, connection, *, device_id: str, events) -> dict:
        summary = {"applied": 0, "duplicate": 0, "unmatched": 0, "rejected": 0, "messages": []}
        with HRUnitOfWork(connection) as uow:
            device = uow.time_clock.get_device(device_id)
        if device is None or not device.active:
            raise HRDomainError("El checador no existe o está inactivo")
        for event in events:
            status, message = self._one(connection, device, event)
            summary[status.value.lower()] += 1
            if message:
                summary["messages"].append(message)
        return summary

    def _one(self, connection, device: TimeClockDevice, event: DeviceAttendanceEvent):
        with HRUnitOfWork(connection) as uow:
            if uow.time_clock.find_event(device.id, event.device_event_id) is not None:
                return DeviceEventStatus.DUPLICATE, ""
            key = credential_key(event.credential_type, event.raw_value)
            moment = event.occurred_at
            if moment.tzinfo is None:   # el aparato da hora local de la sucursal
                moment = moment.replace(tzinfo=resolve_timezone(
                    uow.calendar.timezone_name(device.branch_id)))
            employee_id = uow.time_clock.find_employee_for(event.credential_type, key, device.id)
            if employee_id is None:
                uow.time_clock.save_event(
                    device_id=device.id, device_event_id=event.device_event_id,
                    credential_type=event.credential_type.value, lookup_key=key,
                    occurred_at=moment.isoformat(), kind=event.kind.value,
                    verify_method=event.verify_method,
                    status=DeviceEventStatus.UNMATCHED.value, employee_id=None,
                    punch_id=None, error="Credencial sin empleado")
                return DeviceEventStatus.UNMATCHED, "Credencial no registrada"
            status, message, punch_id = self._apply(connection, uow, device, event, moment,
                                                    employee_id)
            uow.time_clock.save_event(
                device_id=device.id, device_event_id=event.device_event_id,
                credential_type=event.credential_type.value, lookup_key=key,
                occurred_at=moment.isoformat(), kind=event.kind.value,
                verify_method=event.verify_method, status=status.value,
                employee_id=employee_id, punch_id=punch_id,
                error=None if status is DeviceEventStatus.APPLIED else message)
            return status, message

    def _apply(self, connection, uow, device, event, moment, employee_id):
        zone = resolve_timezone(uow.calendar.timezone_name(device.branch_id))
        local_day = moment.astimezone(zone).date()
        open_workday = uow.attendance.find_open_workday(employee_id,
                                                        since=local_day - timedelta(days=1))
        punch_type = event.punch_type(has_open_entry=open_workday is not None)
        registration = self._register.execute(
            connection, employee_id=employee_id, branch_id=device.branch_id,
            punch_type=punch_type, occurred_at=moment, source=device.source,
            operation_id=derived_uuidv7(f"{device.id}|{event.device_event_id}", "hr-device"),
            source_reference_id=f"{device.code}:{event.device_event_id}",
            device_id=device.id, notes=f"Checador {device.code}")
        result = registration.result
        if not result.success:
            return DeviceEventStatus.REJECTED, result.message, None
        return DeviceEventStatus.APPLIED, result.message, result.entity_id


def reprocess_unmatched(connection, *, lookup_key: str | None = None) -> int:
    """Aplica los eventos UNMATCHED cuya credencial ya tiene empleado."""
    ingest = IngestDeviceEventsUseCase()
    with HRUnitOfWork(connection) as uow:
        rows = uow.time_clock.unmatched_events(lookup_key=lookup_key)
    applied = 0
    for row in rows:
        with HRUnitOfWork(connection) as uow:
            device = uow.time_clock.get_device(row["device_id"])
            credential_type = CredentialType(row["credential_type"])
            employee_id = uow.time_clock.find_employee_for(credential_type, row["lookup_key"],
                                                           row["device_id"])
            if device is None or employee_id is None:
                continue
            event = DeviceAttendanceEvent(
                row["device_event_id"], credential_type, row["lookup_key"],
                datetime.fromisoformat(row["occurred_at"]), DeviceEventKind(row["kind"]),
                row["verify_method"])
            status, message, punch_id = ingest._apply(
                connection, uow, device, event, event.occurred_at, employee_id)
            uow.time_clock.resolve_event(row["id"], status=status.value,
                                         employee_id=employee_id, punch_id=punch_id,
                                         error=None if status is DeviceEventStatus.APPLIED
                                         else message)
            applied += status is DeviceEventStatus.APPLIED
    return applied


class EnrollCredentialUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, employee_id: str,
                credential_type: str, raw_value: str, device_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.TIME_CLOCK_MANAGE)
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND")
            self._auth.require_branch(actor_user_id, employee.branch_id)
            try:
                kind = CredentialType(credential_type)
                credential = EmployeeCredential.enroll(employee_id, kind, raw_value,
                                                       device_id=device_id or None,
                                                       enrolled_by_user_id=actor_user_id)
            except (HRDomainError, ValueError) as exc:
                return HRResult.fail(str(exc), "VALIDATION")
            owner = uow.time_clock.find_employee_for(kind, credential.lookup_key, device_id)
            if owner is not None:
                return HRResult.fail("Esa credencial ya pertenece a otro empleado"
                                     if owner != employee_id else "La credencial ya estaba dada de alta",
                                     "DUPLICATE_CREDENTIAL")
            uow.time_clock.save_credential(credential)
            uow.audit.record(action="TIME_CLOCK_CREDENTIAL_ENROLLED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=employee_id,
                             detail=f"{kind.value} {credential.label}")
        applied = reprocess_unmatched(connection, lookup_key=credential.lookup_key)
        message = "Credencial dada de alta"
        if applied:
            message += f"; se aplicaron {applied} marcación(es) que esperaban esta credencial"
        return HRResult.ok(message, entity_id=credential.id, reprocessed=applied)


class RevokeCredentialUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, credential_id: str,
                reason: str) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.TIME_CLOCK_MANAGE)
        if not str(reason or "").strip():
            return HRResult.fail("Dar de baja una credencial requiere motivo", "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            row = uow.time_clock.get_credential(credential_id)
            if row is None:
                return HRResult.fail("La credencial no existe", "NOT_FOUND")
            employee = uow.employees.get(row["employee_id"])
            self._auth.require_branch(actor_user_id, employee.branch_id if employee else "")
            uow.time_clock.revoke_credential(credential_id)
            uow.audit.record(action="TIME_CLOCK_CREDENTIAL_REVOKED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=row["employee_id"],
                             detail=reason.strip())
        return HRResult.ok("Credencial dada de baja", entity_id=credential_id)


class KioskPunchUseCase:
    """Lector USB tipo teclado (tarjeta, QR) o PIN en una estación "checador":
    cada lectura es un evento del aparato del kiosco."""

    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._ingest = IngestDeviceEventsUseCase()

    def execute(self, connection, *, actor_user_id: str, device_id: str,
                credential_type: str, raw_value: str, now: datetime | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.TIME_CLOCK_PUNCH)
        now = now or datetime.now(timezone.utc)
        try:
            kind = CredentialType(credential_type)
            key = credential_key(kind, raw_value)
        except (HRDomainError, ValueError) as exc:
            return HRResult.fail(str(exc), "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            device = uow.time_clock.get_device(device_id)
            if device is None or not device.active:
                return HRResult.fail("El checador no está dado de alta o está inactivo",
                                     "NOT_FOUND")
            self._auth.require_branch(actor_user_id, device.branch_id)
            employee_id = uow.time_clock.find_employee_for(kind, key, device.id)
            if employee_id is not None:
                recent = connection.execute(
                    "SELECT occurred_at FROM attendance_punches WHERE employee_id=?"
                    " ORDER BY occurred_at DESC LIMIT 1", (employee_id,)).fetchone()
                if recent and (now - datetime.fromisoformat(recent[0])).total_seconds() \
                        < DUPLICATE_SCAN_SECONDS:
                    return HRResult.ok("Ya habías checado hace un momento; no se duplicó",
                                       duplicated=True)
        event = DeviceAttendanceEvent(new_uuid(), kind, raw_value, now)
        summary = self._ingest.execute(connection, device_id=device_id, events=[event])
        if summary["unmatched"]:
            return HRResult.fail("Credencial no registrada. Pide a RR. HH. que la dé de alta.",
                                 "UNMATCHED")
        if summary["rejected"]:
            return HRResult.fail(summary["messages"][0], "REJECTED")
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id) if employee_id else None
        name = employee.full_name if employee else ""
        message = summary["messages"][0] if summary["messages"] else "Marcación registrada"
        return HRResult.ok(f"{name}: {message}".strip(": "), employee_name=name)


class SyncTimeClockDeviceUseCase:
    """Descarga los eventos nuevos de un checador de red con su controlador."""

    def __init__(self, authorization: AuthorizationPolicy | None = None, *, drivers: dict) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._drivers = drivers
        self._ingest = IngestDeviceEventsUseCase()

    def execute(self, connection, *, actor_user_id: str, device_id: str) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.TIME_CLOCK_PUNCH)
        with HRUnitOfWork(connection) as uow:
            device = uow.time_clock.get_device(device_id)
            zone_name = uow.calendar.timezone_name(device.branch_id) if device else None
        if device is None:
            return HRResult.fail("El checador no existe", "NOT_FOUND")
        self._auth.require_branch(actor_user_id, device.branch_id)
        driver = self._drivers.get(device.driver)
        if driver is None:
            return HRResult.fail(f"No hay controlador instalado para «{device.driver}»",
                                 "NO_DRIVER")
        try:
            events, cursor = driver.fetch_events(device, device.sync_cursor,
                                                 tz=resolve_timezone(zone_name))
        except Exception as exc:  # aparato apagado, red, archivo: mensaje legible
            return HRResult.fail(f"No se pudo leer el checador {device.code}: {exc}",
                                 "DEVICE_UNAVAILABLE")
        summary = self._ingest.execute(connection, device_id=device_id, events=events)
        with HRUnitOfWork(connection) as uow:
            uow.time_clock.update_sync(device_id, cursor=cursor)
        return HRResult.ok(_summary_text(summary), entity_id=device_id, **summary)


class ImportTimeClockFileUseCase:
    """Importa el archivo de marcaciones que exporta el checador (USB/memoria)."""

    def __init__(self, authorization: AuthorizationPolicy | None = None, *, parser) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._parse = parser
        self._ingest = IngestDeviceEventsUseCase()

    def execute(self, connection, *, actor_user_id: str, device_id: str, path: str) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.TIME_CLOCK_PUNCH)
        with HRUnitOfWork(connection) as uow:
            device = uow.time_clock.get_device(device_id)
            zone_name = uow.calendar.timezone_name(device.branch_id) if device else None
        if device is None:
            return HRResult.fail("El checador no existe", "NOT_FOUND")
        self._auth.require_branch(actor_user_id, device.branch_id)
        try:
            events = self._parse(path, tz=resolve_timezone(zone_name))
        except (OSError, ValueError, HRDomainError) as exc:
            return HRResult.fail(f"No se pudo leer el archivo: {exc}", "VALIDATION")
        summary = self._ingest.execute(connection, device_id=device_id, events=events)
        return HRResult.ok(_summary_text(summary), entity_id=device_id, **summary)


def _summary_text(summary: dict) -> str:
    text = (f"{summary['applied']} marcación(es) aplicadas, {summary['duplicate']} ya "
            f"importadas, {summary['unmatched']} sin empleado, {summary['rejected']} rechazadas")
    return text
