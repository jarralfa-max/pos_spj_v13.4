# tests/test_uc_finanzas.py — SPJ POS v13.5
"""Tests para GestionarFinanzasUC."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_finance():
    f = MagicMock()
    f.registrar_asiento.return_value = 42
    f.get_saldo_caja.return_value = 5000.0
    f.get_total_cxc.return_value = 1200.0
    f.get_total_cxp.return_value = 800.0
    return f

@pytest.fixture
def mock_caja():
    c = MagicMock()
    c.cerrar_turno.return_value = {"total_ventas": 3000.0, "turno_id": 1}
    return c

@pytest.fixture
def uc(mock_finance, mock_caja):
    from core.use_cases.finanzas import GestionarFinanzasUC
    return GestionarFinanzasUC(finance_service=mock_finance, caja_service=mock_caja)

class TestCierreCaja:
    def test_cierre_ok(self, uc):
        from core.use_cases.finanzas import SolicitudCierreCaja
        sol = SolicitudCierreCaja(sucursal_id=1, turno_id=1, efectivo_contado=3000.0, usuario="admin")
        result = uc.cierre_caja(sol)
        assert result.ok is True

    def test_cierre_calcula_diferencia(self, uc):
        from core.use_cases.finanzas import SolicitudCierreCaja
        sol = SolicitudCierreCaja(sucursal_id=1, turno_id=1, efectivo_contado=3100.0, usuario="admin")
        result = uc.cierre_caja(sol)
        assert result.diferencia == 100.0

    def test_cierre_registra_asiento_cuando_hay_diferencia(self, uc, mock_finance):
        from core.use_cases.finanzas import SolicitudCierreCaja
        sol = SolicitudCierreCaja(sucursal_id=1, turno_id=1, efectivo_contado=2900.0, usuario="admin")
        uc.cierre_caja(sol)
        mock_finance.registrar_asiento.assert_called()

    def test_cierre_sin_caja_service(self, mock_finance):
        from core.use_cases.finanzas import GestionarFinanzasUC, SolicitudCierreCaja
        uc = GestionarFinanzasUC(finance_service=mock_finance, caja_service=None)
        sol = SolicitudCierreCaja(sucursal_id=1, turno_id=1, efectivo_contado=0.0, usuario="admin")
        result = uc.cierre_caja(sol)
        assert result.ok is False

class TestConsultarBalance:
    def test_balance_ok(self, uc):
        result = uc.consultar_balance(sucursal_id=1)
        assert result.ok is True
        assert result.saldo_caja == 5000.0

    def test_balance_sin_finance(self):
        from core.use_cases.finanzas import GestionarFinanzasUC
        uc = GestionarFinanzasUC(finance_service=None)
        result = uc.consultar_balance(1)
        assert result.ok is False

class TestAsientoManual:
    def test_asiento_ok(self, uc, mock_finance):
        result = uc.registrar_asiento_manual("1101", "3101", "Aportación capital", 10000.0, 1, "admin")
        assert result["ok"] is True
        mock_finance.registrar_asiento.assert_called()

    def test_asiento_monto_cero_rechazado(self, uc):
        result = uc.registrar_asiento_manual("1101", "3101", "Test", 0.0)
        assert result["ok"] is False

    def test_asiento_sin_finance(self):
        from core.use_cases.finanzas import GestionarFinanzasUC
        uc = GestionarFinanzasUC(finance_service=None)
        result = uc.registrar_asiento_manual("1101", "3101", "X", 100.0)
        assert result["ok"] is False
