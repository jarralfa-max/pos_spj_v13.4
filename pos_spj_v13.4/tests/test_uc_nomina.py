# tests/test_uc_nomina.py — SPJ POS v13.5
"""Tests unitarios para GestionarNominaUC."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock

from core.use_cases.nomina import (
    GestionarNominaUC, SolicitudNomina, ResultadoNomina,
)
from core.rrhh.events import NOMINA_GENERADA, NOMINA_PAGADA


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

    def _procesar(datos_nomina, **kwargs):
        datos_nomina["payroll_payment_id"] = 77
        return "Nómina pagada y notificada correctamente."

    rrhh.procesar_pago_nomina.side_effect = _procesar

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
        operation_id="op-nomina-001",
    )


class TestGestionarNominaUC:

    def test_ejecutar_llama_calcular_nomina(self):
        uc, rrhh, *_ = _make_uc()
        uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        rrhh.calcular_nomina.assert_called_once_with(1, "2026-04-01", "2026-04-15")

    def test_ejecutar_llama_procesar_pago_con_operation_id_y_sin_eventos_directos(self):
        uc, rrhh, *_ = _make_uc()
        uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        rrhh.procesar_pago_nomina.assert_called_once()
        kwargs = rrhh.procesar_pago_nomina.call_args.kwargs
        assert kwargs["operation_id"] == "op-nomina-001"
        assert kwargs["publish_events"] is False

    def test_uc_no_registra_asientos_directos_finanzas_consume_eventos(self):
        uc, _, finance, *_ = _make_uc()
        uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        finance.registrar_asiento.assert_not_called()

    def test_empleado_inexistente_retorna_error(self):
        uc, *_ = _make_uc(calcular_raises=ValueError("Empleado no encontrado."))
        res = uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        assert res.ok is False
        assert "Empleado" in res.error or "encontrado" in res.error.lower()

    def test_publica_nomina_generada_y_pagada(self):
        uc, _, _, _, bus = _make_uc()
        uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        eventos = [call.args[0] for call in bus.publish.call_args_list]
        assert eventos == [NOMINA_GENERADA, NOMINA_PAGADA]
        payload_generada = bus.publish.call_args_list[0].args[1]
        payload_pagada = bus.publish.call_args_list[1].args[1]
        assert payload_generada["operation_id"] == "op-nomina-001"
        assert payload_generada["total"] == 2000.0
        assert payload_generada["neto"] == 1820.0
        assert payload_generada["payroll_payment_id"] == 77
        assert payload_pagada["payroll_payment_id"] == 77
        assert payload_pagada["total"] == 2000.0
        assert payload_pagada["neto"] == 1820.0

    def test_neto_deducido_correcto_en_resultado(self):
        uc, *_ = _make_uc()
        res = uc.ejecutar(_solicitud(), sucursal_id=1, admin_user="admin")
        assert res.ok is True
        assert res.neto_deducido == 1820.0
        assert res.imss_patronal == 350.0
        assert res.nombre_completo == "Ana García"
        assert res.payroll_payment_id == 77
        assert res.operation_id == "op-nomina-001"
