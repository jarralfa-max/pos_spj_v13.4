"""Probar un dispositivo configurado (Configuración → Dispositivos → Pruebas).

Antes no había ninguna forma de comprobar desde la aplicación que una
impresora dada de alta respondía: `PrinterTestResult`/`DeviceTestResult` y sus
tablas existían sin un solo escritor, y lo primero que avisaba de un error de
configuración era el cajero sin ticket.

Dos pruebas, por la MISMA vía de entrega que usan Ventas y Caja
(`backend/infrastructure/printing/routed_printer.py`), así que si la prueba
pasa, el ticket sale:
- CONNECTIVITY — no imprime: abre la conexión (red, serie) o consulta la
  impresora instalada en Windows y su estado.
- TEST_PRINT — imprime una página corta. Es invasiva: la pantalla la confirma
  antes (§21).
Cada intento queda en el historial (`device_test_results`).

Por ahora sólo hay prueba automática para impresoras; básculas, lectores y
demás no tienen todavía un controlador real contra el cual probar.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from backend.domain.device_management.entities.device_test_result import DeviceTestResult
from backend.domain.device_management.enums import PRINTER_DEVICE_TYPES, DeviceStatus
from backend.domain.device_management.exceptions import DeviceInvalidValueError, DeviceNotFoundError
from backend.infrastructure.db.repositories.device_management.device_test_result_repository import (
    SqliteDeviceTestResultRepository,
)
from backend.infrastructure.printing import routed_printer
from backend.infrastructure.printing.diagnostic_page_renderer import render_diagnostic_page


class DeviceTestType(str, Enum):
    CONNECTIVITY = "CONNECTIVITY"
    TEST_PRINT = "TEST_PRINT"


class TestDeviceUseCase:
    __test__ = False  # no es una prueba de pytest pese al nombre

    def __init__(self, connection) -> None:
        self._conn = connection
        self._results = SqliteDeviceTestResultRepository(connection)

    def execute(self, *, device_id: str, test_type: DeviceTestType | str,
                actor_user_id: str | None = None) -> DeviceTestResult:
        test_type = DeviceTestType(test_type)
        try:
            device, profile = routed_printer.load_device(
                self._conn, device_id, no_printer_message="El dispositivo no existe.")
        except routed_printer.PrintTargetUnavailable as exc:
            raise DeviceNotFoundError(str(exc)) from exc
        if device.status is DeviceStatus.RETIRED:
            raise DeviceInvalidValueError(f"{device.code} está retirado; no se prueba.")
        if profile.device_type not in PRINTER_DEVICE_TYPES:
            raise DeviceInvalidValueError(
                "Por ahora la prueba automática sólo existe para impresoras.")

        if test_type is DeviceTestType.CONNECTIVITY:
            try:
                success, message = routed_printer.probe(device, profile)
            except routed_printer.PrintTargetUnavailable as exc:
                success, message = False, str(exc)
        else:
            success, message = self._print_page(device, profile)

        result = DeviceTestResult.record(
            device_id=device.id, test_type=test_type.value, success=success, message=message,
            tested_by_user_id=actor_user_id or None)
        self._results.save(result)
        self._conn.commit()
        return result

    @staticmethod
    def _print_page(device, profile) -> tuple[bool, str]:
        try:
            transport, _destination, _baud = routed_printer.connection_target(device, profile)
            data = render_diagnostic_page(
                device_code=device.code, device_name=device.name,
                connection=getattr(transport, "value", str(transport)),
                paper_width_mm=routed_printer.paper_width_mm(profile),
                printed_at=datetime.now(timezone.utc).astimezone())
            routed_printer.send(device, profile, data, what="la página de prueba")
        except routed_printer.PrintTargetUnavailable as exc:
            return False, str(exc)
        return True, f"Página de prueba enviada a {device.code}."
