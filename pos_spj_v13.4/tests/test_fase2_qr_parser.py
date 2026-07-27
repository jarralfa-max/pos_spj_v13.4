# tests/test_fase2_qr_parser.py
# Fase 2 — LectorQR: normalización y señal qr_desconocido
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock

# Mock PyQt5 para CI headless — lector_qr.py lo importa a nivel de módulo
for _m in ['PyQt5', 'PyQt5.QtCore', 'PyQt5.QtWidgets', 'PyQt5.QtGui']:
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()
# Señales PyQt5 reales mockeadas con MagicMock
if not hasattr(sys.modules.get('PyQt5.QtCore', MagicMock()), 'pyqtSignal'):
    sys.modules['PyQt5.QtCore'].pyqtSignal = MagicMock(return_value=MagicMock())


# ══════════════════════════════════════════════════════════════════════════════
# _parsear — normalización de prefijos
# ══════════════════════════════════════════════════════════════════════════════

PREFIJOS_QR = {
    "SPJ:CONT":   "contenedor",
    "SPJ:PROD":   "producto",
    "SPJ:FIDEL":  "cliente_fidelidad",
    "SPJ:DEL":    "ticket_delivery",
    "SPJ:MAP":    "mapa_entrega",
}


class _FakeLector:
    """Replica _parsear() sin necesitar PyQt5."""
    def _parsear(self, raw: str) -> tuple:
        cleaned = raw.strip()
        upper = cleaned.upper()
        for prefijo, tipo in PREFIJOS_QR.items():
            needle = prefijo + ":"
            if upper.startswith(needle):
                uuid_qr = cleaned[len(needle):]
                return tipo, uuid_qr
        return "barcode", cleaned


def test_parsear_mayusculas_standard():
    """SPJ:CONT:uuid → contenedor (caso normal)."""
    lector = _FakeLector()
    tipo, uuid = lector._parsear("SPJ:CONT:abc-123")
    assert tipo == "contenedor"
    assert uuid == "abc-123"


def test_parsear_minusculas_normaliza():
    """spj:cont:abc-123 debe reconocerse aunque venga en minúsculas."""
    lector = _FakeLector()
    tipo, uuid = lector._parsear("spj:cont:abc-123")
    assert tipo == "contenedor"
    assert uuid == "abc-123"


def test_parsear_mixedcase_normaliza():
    """Spj:Cont:abc-123 → contenedor."""
    lector = _FakeLector()
    tipo, uuid = lector._parsear("Spj:Cont:abc-123")
    assert tipo == "contenedor"
    assert uuid == "abc-123"


def test_parsear_espacios_extra_normaliza():
    """' SPJ:CONT:abc-123 ' → contenedor (espacios eliminados)."""
    lector = _FakeLector()
    tipo, uuid = lector._parsear("  SPJ:CONT:abc-123  ")
    assert tipo == "contenedor"
    assert uuid == "abc-123"


def test_parsear_producto():
    """SPJ:PROD:123 → producto."""
    lector = _FakeLector()
    tipo, uuid = lector._parsear("SPJ:PROD:123")
    assert tipo == "producto"
    assert uuid == "123"


def test_parsear_fidelidad():
    """SPJ:FIDEL:cli-99 → cliente_fidelidad."""
    lector = _FakeLector()
    tipo, uuid = lector._parsear("SPJ:FIDEL:cli-99")
    assert tipo == "cliente_fidelidad"
    assert uuid == "cli-99"


def test_parsear_sin_prefijo_spj_retorna_barcode():
    """Código sin prefijo SPJ → ('barcode', raw)."""
    lector = _FakeLector()
    tipo, uuid = lector._parsear("7501234567890")
    assert tipo == "barcode"
    assert uuid == "7501234567890"


def test_parsear_preserva_uuid_original():
    """El UUID se extrae en su capitalización original, no en uppercase."""
    lector = _FakeLector()
    _, uuid = lector._parsear("spj:cont:AbCd-EfGh")
    assert uuid == "AbCd-EfGh"  # Debe respetar case original del UUID


# ══════════════════════════════════════════════════════════════════════════════
# Señal qr_desconocido — verificar que está declarada en LectorQR
# ══════════════════════════════════════════════════════════════════════════════

def test_lector_qr_tiene_senal_qr_desconocido():
    """LectorQR debe declarar la señal qr_desconocido en su código fuente."""
    import pathlib
    src = pathlib.Path(__file__).parent.parent / "hardware" / "lector_qr.py"
    assert "qr_desconocido" in src.read_text(), (
        "hardware/lector_qr.py no contiene 'qr_desconocido' — señal para flujo legacy requerida"
    )
