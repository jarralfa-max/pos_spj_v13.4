# tests/test_fase1_printer_transport.py
# Fase 1 — PrinterService: canal FILE, null-guard pyserial, detección de transporte
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch


# ══════════════════════════════════════════════════════════════════════════════
# TransportType.FILE — detección
# ══════════════════════════════════════════════════════════════════════════════

def test_detect_type_dev_usb():
    """'/dev/usb/lp0' debe detectarse como FILE."""
    from core.services.printer_service import PrintTransport, TransportType
    assert PrintTransport.detect_type("/dev/usb/lp0") == TransportType.FILE


def test_detect_type_prn_extension():
    """Ruta con extensión .prn debe detectarse como FILE."""
    from core.services.printer_service import PrintTransport, TransportType
    assert PrintTransport.detect_type("/tmp/spool.prn") == TransportType.FILE


def test_detect_type_relative_path():
    """Ruta relativa './impresora.bin' debe detectarse como FILE."""
    from core.services.printer_service import PrintTransport, TransportType
    assert PrintTransport.detect_type("./impresora.bin") == TransportType.FILE


def test_detect_type_absolute_path():
    """Ruta absoluta genérica '/tmp/printer_spool' → FILE."""
    from core.services.printer_service import PrintTransport, TransportType
    assert PrintTransport.detect_type("/tmp/printer_spool") == TransportType.FILE


def test_detect_type_network():
    """'192.168.1.100:9100' debe detectarse como NETWORK."""
    from core.services.printer_service import PrintTransport, TransportType
    assert PrintTransport.detect_type("192.168.1.100:9100") == TransportType.NETWORK


def test_detect_type_serial():
    """'/dev/ttyUSB0' debe detectarse como SERIAL."""
    from core.services.printer_service import PrintTransport, TransportType
    assert PrintTransport.detect_type("/dev/ttyUSB0") == TransportType.SERIAL


def test_detect_type_fallback_usb_win32():
    """Destino vacío → USB_WIN32 (fallback)."""
    from core.services.printer_service import PrintTransport, TransportType
    assert PrintTransport.detect_type("") == TransportType.USB_WIN32


# ══════════════════════════════════════════════════════════════════════════════
# _send_file — escritura real a archivo temporal
# ══════════════════════════════════════════════════════════════════════════════

def test_send_file_escribe_bytes():
    """_send_file() escribe bytes exactos al archivo destino."""
    from core.services.printer_service import PrintTransport
    data = b"\x1b\x40Hello SPJ\x0a"
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        path = tmp.name
    try:
        result = PrintTransport._send_file(data, path)
        assert result is True
        with open(path, 'rb') as f:
            assert f.read() == data
    finally:
        os.unlink(path)


def test_send_file_retorna_true():
    """_send_file() retorna True al escribir correctamente."""
    from core.services.printer_service import PrintTransport
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        path = tmp.name
    try:
        assert PrintTransport._send_file(b"test", path) is True
    finally:
        os.unlink(path)


# ══════════════════════════════════════════════════════════════════════════════
# _send_serial — null-guard cuando pyserial no está instalado
# ══════════════════════════════════════════════════════════════════════════════

def test_send_serial_sin_pyserial_retorna_false():
    """Si pyserial no está disponible, _send_serial() retorna False sin lanzar."""
    from core.services.printer_service import PrintTransport
    with patch.dict("sys.modules", {"serial": None}):
        result = PrintTransport._send_serial(b"test", "/dev/ttyUSB0")
    assert result is False


def test_send_serial_importerror_no_lanza():
    """_send_serial() no debe propagar ImportError cuando serial=None."""
    from core.services.printer_service import PrintTransport
    try:
        with patch.dict("sys.modules", {"serial": None}):
            PrintTransport._send_serial(b"test", "/dev/ttyUSB0")
    except ImportError:
        pytest.fail("_send_serial() propagó ImportError")


# ══════════════════════════════════════════════════════════════════════════════
# TransportType enum — FILE está presente
# ══════════════════════════════════════════════════════════════════════════════

def test_transport_type_file_existe():
    """TransportType.FILE debe existir y tener valor 'file'."""
    from core.services.printer_service import TransportType
    assert TransportType.FILE == "file"
