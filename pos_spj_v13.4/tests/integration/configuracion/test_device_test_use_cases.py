"""Probar un dispositivo configurado (Configuración → Dispositivos → Pruebas).

Antes no había forma de comprobar desde la aplicación que una impresora dada de
alta respondía. Aquí `PrintTransport` está interceptado SIEMPRE: la instalación
real tiene una impresora USB predeterminada y ninguna prueba debe imprimir.
"""

from __future__ import annotations

import pytest

from backend.application.queries.configuracion.workspace_query_service import (
    ConfiguracionWorkspaceQueryService,
)
from backend.application.use_cases.configuracion.device_test_use_cases import TestDeviceUseCase
from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import ConnectionType, DeviceType
from backend.domain.device_management.exceptions import DeviceInvalidValueError
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.device_management.value_objects.network_endpoint import NetworkEndpoint
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import (
    SqliteDeviceRepository,
)
from backend.infrastructure.printing import transport
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    c = make_db()
    yield c
    c.close()


@pytest.fixture
def wire(monkeypatch):
    """Lo que la "impresora" recibió y cómo responde la sonda."""
    estado = {"sent": [], "probe": (True, "acepta conexiones"), "send_ok": True}
    monkeypatch.setattr(transport.PrintTransport, "send", classmethod(
        lambda cls, data, kind, destination, baud=9600:
        estado["sent"].append((kind, destination, data)) or estado["send_ok"]))
    monkeypatch.setattr(transport.PrintTransport, "probe", classmethod(
        lambda cls, kind, destination, baud=9600: estado["probe"]))
    return estado


def _device(conn, device_type=DeviceType.THERMAL_PRINTER, code="PRN-01"):
    branch = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
    profile = DeviceProfile.create(
        name="Térmica de red", device_type=device_type,
        connection_profile=ConnectionProfile.create(
            ConnectionType.NETWORK, network_endpoint=NetworkEndpoint.create(host="10.0.0.9", port=9100)),
        paper_profile="80mm" if device_type is DeviceType.THERMAL_PRINTER else None,
        protocol="ESC_POS" if device_type is DeviceType.THERMAL_PRINTER else "")
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch, profile_id=profile.id, code=code, name="Caja 1")
    SqliteDeviceRepository(conn).save(device)
    conn.commit()
    return device


def test_connection_test_does_not_print_and_is_recorded(conn, wire):
    device = _device(conn)
    result = TestDeviceUseCase(conn).execute(device_id=device.id, test_type="CONNECTIVITY")
    assert result.success and wire["sent"] == []
    historial = ConfiguracionWorkspaceQueryService(conn, None).list_device_tests(device.id)
    assert [(h.test, h.result) for h in historial] == [("Conexión", "Éxito")]


def test_an_unreachable_printer_is_a_recorded_failure(conn, wire):
    wire["probe"] = (False, "10.0.0.9:9100 no responde")
    device = _device(conn)
    result = TestDeviceUseCase(conn).execute(device_id=device.id, test_type="CONNECTIVITY")
    assert not result.success and "no responde" in result.message


def test_the_test_page_goes_to_the_configured_printer(conn, wire):
    device = _device(conn)
    result = TestDeviceUseCase(conn).execute(device_id=device.id, test_type="TEST_PRINT")
    assert result.success
    [(kind, destination, data)] = wire["sent"]
    assert destination == "10.0.0.9:9100" and b"PRUEBA DE IMPRESION" in data and b"PRN-01" in data


def test_a_printer_that_does_not_accept_the_page_fails(conn, wire):
    wire["send_ok"] = False
    result = TestDeviceUseCase(conn).execute(device_id=_device(conn).id, test_type="TEST_PRINT")
    assert not result.success and "no recibió" in result.message


def test_only_printers_have_an_automatic_test_for_now(conn, wire):
    scale = _device(conn, DeviceType.SCALE, code="BAS-01")
    with pytest.raises(DeviceInvalidValueError, match="impresoras"):
        TestDeviceUseCase(conn).execute(device_id=scale.id, test_type="CONNECTIVITY")


# ── impresora de Windows (USB) ────────────────────────────────────────────────
def _usb_device(conn, windows_printer=""):
    branch = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
    profile = DeviceProfile.create(
        name="Térmica USB", device_type=DeviceType.THERMAL_PRINTER,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
        paper_profile="80mm", protocol="ESC_POS", driver_name=windows_printer)
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch, profile_id=profile.id, code="PRN-USB", name="TL2X")
    SqliteDeviceRepository(conn).save(device)
    conn.commit()
    return device


def test_usb_printing_goes_to_the_profile_windows_queue(conn, wire):
    """Antes todo USB iba a la predeterminada de Windows (en la instalación real,
    «Microsoft Print to PDF»), aunque la térmica fuera otra cola."""
    device = _usb_device(conn, windows_printer="TL2X Printer")
    TestDeviceUseCase(conn).execute(device_id=device.id, test_type="TEST_PRINT")
    [(kind, destination, _data)] = wire["sent"]
    assert (kind.value, destination) == ("usb_win32", "TL2X Printer")


def test_choosing_the_windows_printer_only_accepts_installed_ones(conn):
    from backend.application.use_cases.configuracion.device_management_use_cases import (
        SetDeviceWindowsPrinterUseCase,
    )
    instaladas = lambda: ("Microsoft Print to PDF", "TL2X Printer")  # noqa: E731
    device = _usb_device(conn)
    with pytest.raises(DeviceInvalidValueError, match="no está instalada"):
        SetDeviceWindowsPrinterUseCase(conn, instaladas).execute(
            device_id=device.id, printer_name="Otra")
    profile = SetDeviceWindowsPrinterUseCase(conn, instaladas).execute(
        device_id=device.id, printer_name="TL2X Printer")
    assert profile.driver_name == "TL2X Printer"
    with pytest.raises(DeviceInvalidValueError, match="USB"):
        SetDeviceWindowsPrinterUseCase(conn, instaladas).execute(
            device_id=_device(conn, code="PRN-NET").id, printer_name="TL2X Printer")


def test_the_usb_probe_fails_and_says_which_default_would_be_used(monkeypatch):
    import sys
    import types

    from backend.infrastructure.printing.transport import PrintTransport, TransportType

    falso = types.SimpleNamespace(
        GetDefaultPrinter=lambda: "Microsoft Print to PDF", OpenPrinter=lambda name: name,
        GetPrinter=lambda handle, level: {"Status": 0}, ClosePrinter=lambda handle: None)
    monkeypatch.setitem(sys.modules, "win32print", falso)
    ok, message = PrintTransport.probe(TransportType.USB_WIN32, "")
    assert not ok and "Microsoft Print to PDF" in message and "predeterminada" in message
    ok, message = PrintTransport.probe(TransportType.USB_WIN32, "TL2X Printer")
    assert ok and "TL2X Printer" in message
    falso.GetPrinter = lambda handle, level: {"Status": 0x80}
    ok, message = PrintTransport.probe(TransportType.USB_WIN32, "TL2X Printer")
    assert not ok and "fuera de línea" in message
