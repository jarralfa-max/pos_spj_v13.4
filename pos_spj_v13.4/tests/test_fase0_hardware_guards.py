# tests/test_fase0_hardware_guards.py
# Fase 0 — Bug 4: HardwareService debe manejar serial=None gracefully
# Verifica que read_scale() y open_cash_drawer() retornan valores seguros
# cuando pyserial no está disponible (serial is None).
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import core.services.hardware_service as hw_module


@pytest.fixture
def hw_db():
    """BD en memoria con tabla hardware_config."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE hardware_config (
            tipo            TEXT PRIMARY KEY,
            nombre          TEXT,
            activo          INTEGER DEFAULT 1,
            configuraciones TEXT
        );
        INSERT INTO hardware_config VALUES (
            'bascula', 'Báscula Test', 1,
            '{"puerto": "/dev/ttyUSB0", "baud_rate": 9600}'
        );
        INSERT INTO hardware_config VALUES (
            'cajon', 'Cajón Test', 1,
            '{"metodo": "serial", "puerto": "/dev/ttyUSB1", "baud_rate": 9600}'
        );
    """)
    conn.commit()
    return conn


@pytest.fixture
def hw_service_no_serial(hw_db):
    """HardwareService con serial=None (pyserial no disponible)."""
    original_serial = hw_module.serial
    hw_module.serial = None
    from core.services.hardware_service import HardwareService
    svc = HardwareService(hw_db)
    yield svc
    hw_module.serial = original_serial  # Restaurar al finalizar


def test_read_scale_returns_zero_without_serial(hw_service_no_serial):
    """read_scale() debe retornar 0.0 cuando serial is None."""
    result = hw_service_no_serial.read_scale()
    assert result == 0.0, f"Esperado 0.0 con serial=None, se obtuvo {result}"


def test_read_scale_no_exception_without_serial(hw_service_no_serial):
    """read_scale() no debe lanzar ninguna excepción cuando serial is None."""
    try:
        hw_service_no_serial.read_scale()
    except Exception as e:
        pytest.fail(f"read_scale() lanzó excepción inesperada con serial=None: {e}")


def test_open_cash_drawer_serial_returns_false_without_serial(hw_service_no_serial):
    """open_cash_drawer() con método 'serial' debe retornar False cuando serial is None."""
    result = hw_service_no_serial.open_cash_drawer()
    assert result is False, (
        f"open_cash_drawer() debe retornar False con serial=None, se obtuvo {result}"
    )


def test_open_cash_drawer_no_exception_without_serial(hw_service_no_serial):
    """open_cash_drawer() no debe lanzar excepción cuando serial is None."""
    try:
        hw_service_no_serial.open_cash_drawer()
    except Exception as e:
        pytest.fail(f"open_cash_drawer() lanzó excepción inesperada con serial=None: {e}")


def test_hardware_service_loads_config(hw_db):
    """HardwareService debe cargar correctamente hardware_config de la BD."""
    from core.services.hardware_service import HardwareService
    svc = HardwareService(hw_db)
    assert 'bascula' in svc._cache_config, "Configuración de báscula debe cargarse en cache"
    assert 'cajon' in svc._cache_config, "Configuración de cajón debe cargarse en cache"
    assert svc._cache_config['bascula']['baud_rate'] == 9600


def test_read_scale_zero_without_config(hw_db):
    """read_scale() debe retornar 0.0 si la báscula no está en config."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE hardware_config (tipo TEXT PRIMARY KEY, nombre TEXT, activo INTEGER, configuraciones TEXT);")
    conn.commit()
    from core.services.hardware_service import HardwareService
    svc = HardwareService(conn)
    assert svc.read_scale() == 0.0, "Sin config de báscula debe retornar 0.0"
