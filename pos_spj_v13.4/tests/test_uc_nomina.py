# tests/test_uc_nomina.py — SPJ POS v13.5
"""Tests unitarios para GestionarNominaUC."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, call

from core.use_cases.nomina import (
    GestionarNominaUC, SolicitudNomina, ResultadoNomina,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────

_DATOS_NOMINA = {
    "empleado_id":     1,
    "nombre_completo": "Ana García",
    "telefono":        "5551111111",
    "dias_asistidos":  5,
    "total_horas":     40.0,
    "salario_base":    2000.0,
    "neto_a_pagar":    2000.0,
    "imss_obrero":     100.0,
    "isr_mensual":     80.0,
    "neto_deducido":   1820.0,
    "retenciones": {
        "imss_obrero":   100.0,
        "imss_patronal": 350.0,
        "isr_mensual":    80.0,
    },
}


def _make_uc(calcular_raises=None):
    rrhh = MagicMock()
    if calcular_raises:
        rrhh.calcular_nomina.side_effect = calcular_raises
    else:
        rrhh.calcular_nomina.return_value = _DATOS_NOMINA.copy()
    rrhh.procesar_pago_nomina.return_value = "NOMINA-2024-001"

    finance = MagicMock()
    finance.registrar_asiento.return_value = 55

    hr = MagicMock()
    bus = MagicMock()

    uc = GestionarNominaUC(
        rrhh_service    = rrhh,
        finance_service = finance,
        hr_rule_engine  = hr,
        event_bus       = bus,
    )
    return uc, rrhh, finance, hr, bus


def _solicitud():
    return SolicitudNomina(
        empleado_id=1,
        fecha_inicio="2026-04-01",
        fecha_fin="2026-04-15",
        metodo_pago="efectivo",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGestionarNominaUC:

    def test_ejecutar_llama_calcular_nomina(self):
        uc, rrhh, *_ = _make_uc()
        uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        rrhh.calcular_nomina.assert_called_once_with(1, "2026-04-01", "2026-04-15")

    def test_ejecutar_llama_procesar_pago(self):
        uc, rrhh, *_ = _make_uc()
        uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        rrhh.procesar_pago_nomina.assert_called_once()

    def test_asiento_6101_caja_siempre_registrado(self):
        uc, _, finance, *_ = _make_uc()
        uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        calls = finance.registrar_asiento.call_args_list
        nomina_call = next(
            (c for c in calls if c.kwargs.get("debe") == "6101"), None
        )
        assert nomina_call is not None, "Asiento 6101/1101 no fue registrado"
        assert nomina_call.kwargs.get("haber") == "1101"
        assert nomina_call.kwargs.get("monto") == 1820.0

    def test_asiento_imss_patronal_6102_registrado(self):
        uc, _, finance, *_ = _make_uc()
        uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        calls = finance.registrar_asiento.call_args_list
        imss_call = next(
            (c for c in calls if c.kwargs.get("debe") == "6102"), None
        )
        assert imss_call is not None, "Asiento IMSS patronal no fue registrado"
        assert imss_call.kwargs.get("haber") == "2201"
        assert imss_call.kwargs.get("monto") == 350.0

    def test_empleado_inexistente_retorna_error(self):
        uc, *_ = _make_uc(calcular_raises=ValueError("Empleado no encontrado."))
        res = uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        assert res.ok is False
        assert "Empleado" in res.error or "encontrado" in res.error.lower()

    def test_fallo_asiento_no_bloquea_nomina(self):
        uc, _, finance, *_ = _make_uc()
        finance.registrar_asiento.side_effect = Exception("tabla no existe")
        res = uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        assert res.ok is True
        assert res.neto_deducido == 1820.0

    def test_publica_nomina_pagada(self):
        uc, _, _, _, bus = _make_uc()
        uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        bus.publish.assert_called_once()
        evento = bus.publish.call_args[0][0]
        assert evento == "NOMINA_PAGADA"

    def test_neto_deducido_correcto_en_resultado(self):
        uc, *_ = _make_uc()
        res = uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        assert res.ok is True
        assert res.neto_deducido == 1820.0
        assert res.imss_patronal == 350.0
        assert res.nombre_completo == "Ana García"
