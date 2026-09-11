"""Entrega de bytes a una impresora.

Reemplaza `core/services/printer_service.py::PrintTransport`. Los valores del
enum no se eligieron al reescribirlo: los fija
`tests/integration/test_purchase_cash_ticket_printing.py`, y `_send_win32` lo
exige por nombre el guardrail `test_no_direct_escpos_usb_default.py`.

No se toca hardware real: se sustituye el socket, el puerto serie y win32print.
Lo que se comprueba es lo que se le entrega a cada uno — que es donde están los
fallos que no dan error, como un ticket cortado a la mitad.
"""
from __future__ import annotations

import pytest

from backend.infrastructure.printing.transport import (
    DEFAULT_NETWORK_PORT,
    PrintTransport,
    TransportType,
    save_ticket_document,
)

TICKET = b"\x1b@Hola\n\x1dVA\x00"


# ── contrato que fijan las pruebas supervivientes ───────────────────────────
def test_the_transport_values_are_the_ones_already_stored():
    """Cambiarlos dejaría sin resolver los perfiles de dispositivo guardados."""
    assert TransportType.USB_WIN32.value == "usb_win32"
    assert TransportType.NETWORK.value == "network"
    assert TransportType.SERIAL.value == "serial"


def test_the_windows_usb_path_is_win32print():
    """El guardrail lo exige por nombre: `escpos.Usb` (libusb) obligaría a
    sustituir el driver de la impresora y dejarla inservible para el resto
    del equipo."""
    assert hasattr(PrintTransport, "_send_win32")


# ── red ─────────────────────────────────────────────────────────────────────
class _FakeSocket:
    def __init__(self):
        self.sent = b""
        self.closed = False

    def sendall(self, data):
        self.sent += data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True


@pytest.fixture
def fake_network(monkeypatch):
    registro = {}
    sock = _FakeSocket()

    def _create_connection(address, timeout=None):
        registro["address"] = address
        registro["timeout"] = timeout
        return sock

    monkeypatch.setattr("socket.create_connection", _create_connection)
    registro["socket"] = sock
    return registro


def test_network_delivery_sends_every_byte(fake_network):
    assert PrintTransport.send(TICKET, TransportType.NETWORK, "10.0.0.5:9100") is True
    assert fake_network["socket"].sent == TICKET


def test_network_delivery_uses_the_raw_printing_port_by_default(fake_network):
    """Sin puerto, el 9100: es el de impresión cruda de una térmica de red."""
    PrintTransport.send(TICKET, TransportType.NETWORK, "10.0.0.5")
    assert fake_network["address"] == ("10.0.0.5", DEFAULT_NETWORK_PORT)


def test_network_delivery_has_a_timeout(fake_network):
    """Sin límite, una impresora que no responde cuelga la caja."""
    PrintTransport.send(TICKET, TransportType.NETWORK, "10.0.0.5:9100")
    assert fake_network["timeout"] is not None and fake_network["timeout"] > 0


def test_an_unreachable_printer_reports_failure_instead_of_raising(monkeypatch):
    """Una impresora apagada es operación normal en un mostrador, no un error
    de programa: quien llama decide si reintenta o avisa."""
    def _falla(*_args, **_kwargs):
        raise OSError("conexión rechazada")

    monkeypatch.setattr("socket.create_connection", _falla)
    assert PrintTransport.send(TICKET, TransportType.NETWORK, "10.0.0.5:9100") is False


def test_network_delivery_uses_sendall_not_send(fake_network):
    """`send` puede entregar sólo parte del búfer y devolver cuántos bytes
    escribió: el ticket saldría cortado a la mitad, sin ningún error."""
    sock = fake_network["socket"]
    assert not hasattr(sock, "send")   # el doble sólo expone sendall
    assert PrintTransport.send(TICKET, TransportType.NETWORK, "1.2.3.4") is True


# ── serie ───────────────────────────────────────────────────────────────────
class _FakeSerial:
    instancias = []

    def __init__(self, port, baudrate=9600, timeout=None):
        self.port, self.baudrate = port, baudrate
        self.written, self.flushed = b"", False
        _FakeSerial.instancias.append(self)

    def write(self, data):
        self.written += data

    def flush(self):
        self.flushed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_serial_delivery_passes_the_configured_baud_rate(monkeypatch):
    import types

    _FakeSerial.instancias.clear()
    monkeypatch.setitem(
        __import__("sys").modules, "serial", types.SimpleNamespace(Serial=_FakeSerial))

    assert PrintTransport.send(
        TICKET, TransportType.SERIAL, "COM3", baud=19200) is True
    puerto = _FakeSerial.instancias[-1]
    assert (puerto.port, puerto.baudrate) == ("COM3", 19200)
    assert puerto.written == TICKET


def test_serial_delivery_flushes(monkeypatch):
    """Sin `flush` el búfer puede quedarse a medias al cerrar y el ticket sale
    truncado sin que nada lo reporte."""
    import types

    _FakeSerial.instancias.clear()
    monkeypatch.setitem(
        __import__("sys").modules, "serial", types.SimpleNamespace(Serial=_FakeSerial))

    PrintTransport.send(TICKET, TransportType.SERIAL, "COM3")
    assert _FakeSerial.instancias[-1].flushed is True


# ── archivo ─────────────────────────────────────────────────────────────────
def test_file_delivery_writes_the_exact_bytes(tmp_path):
    destino = tmp_path / "ticket.bin"
    assert PrintTransport.send(TICKET, TransportType.FILE, str(destino)) is True
    assert destino.read_bytes() == TICKET


def test_an_unwritable_destination_reports_failure(tmp_path):
    assert PrintTransport.send(
        TICKET, TransportType.FILE, str(tmp_path / "no" / "existe" / "t.bin")) is False


# ── casos límite ────────────────────────────────────────────────────────────
def test_nothing_to_print_is_not_a_failure(monkeypatch):
    """Y no abre socket ni puerto para no enviar nada."""
    def _no_deberia(*_a, **_k):
        raise AssertionError("no debió abrir ninguna conexión")

    monkeypatch.setattr("socket.create_connection", _no_deberia)
    assert PrintTransport.send(b"", TransportType.NETWORK, "1.2.3.4") is True


def test_an_unsupported_transport_raises_instead_of_silently_dropping():
    """Es un fallo de configuración: callarlo perdería tickets en silencio."""
    with pytest.raises(ValueError):
        PrintTransport.send(TICKET, "telepatia", "destino")


# ── documento del ticket ────────────────────────────────────────────────────
def test_the_ticket_document_is_written_as_html(tmp_path):
    """La función que reemplaza se llamaba `save_ticket_pdf` y escribía HTML.
    Se conserva el comportamiento y se corrige el nombre: un `.pdf` que en
    realidad es HTML no lo abre el visor que le corresponde."""
    destino = tmp_path / "ticket.html"
    devuelto = save_ticket_document("<html><body>F-900</body></html>", str(destino))
    assert devuelto == str(destino)
    assert "F-900" in destino.read_text(encoding="utf-8")


def test_the_ticket_document_keeps_non_ascii_text(tmp_path):
    destino = tmp_path / "t.html"
    save_ticket_document("<p>Jamón · Ñandú</p>", str(destino))
    assert "Jamón · Ñandú" in destino.read_text(encoding="utf-8")
