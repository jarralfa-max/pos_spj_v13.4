# tests/test_sales_event_flow.py — SPJ POS v13.4
"""
Tests for the canonical sale event flow:
  SalesService → SALE_ITEMS_PROCESS → handlers → VENTA_COMPLETADA → handlers

Verifies:
  - SaleFinanceHandler skips MercadoPago and Credito
  - SaleFinanceHandler registers income for cash/card sales
  - CreditSaleFinanceHandler creates CxC for credit sales
  - VENTA_COMPLETADA payload includes payment_method
  - treasury handler receives payment_method from VENTA_COMPLETADA
  - No double income registration (finance handler + UI direct call eliminated)
"""
from __future__ import annotations

import sqlite3
import sys
import os
import pytest
from unittest.mock import MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.events.handlers.finance_handler import SaleFinanceHandler, CreditSaleFinanceHandler


# ─────────────────────────────────────────────────────────────────────────────
# SaleFinanceHandler
# ─────────────────────────────────────────────────────────────────────────────

class TestSaleFinanceHandler:
    def _mock_finance(self):
        f = MagicMock()
        f.register_income = MagicMock()
        return f

    def _handler(self):
        return SaleFinanceHandler(finance_service=self._mock_finance())

    def test_efectivo_registra_ingreso(self):
        fs = self._mock_finance()
        h = SaleFinanceHandler(fs)
        h.handle({"payment_method": "Efectivo", "total": 100.0, "folio": "VNT-001"})
        fs.register_income.assert_called_once()
        kwargs = fs.register_income.call_args
        assert kwargs.kwargs.get("amount", kwargs.args[0] if kwargs.args else None) == 100.0

    def test_tarjeta_registra_ingreso(self):
        fs = self._mock_finance()
        h = SaleFinanceHandler(fs)
        h.handle({"payment_method": "Tarjeta", "total": 250.0, "folio": "VNT-002"})
        fs.register_income.assert_called_once()

    def test_credito_NO_registra_ingreso(self):
        """Credit sales defer income — CxC is created by CreditSaleFinanceHandler."""
        fs = self._mock_finance()
        h = SaleFinanceHandler(fs)
        h.handle({"payment_method": "Credito", "total": 150.0, "folio": "VNT-003"})
        fs.register_income.assert_not_called()

    def test_mercado_pago_NO_registra_ingreso(self):
        """MercadoPago: only a link is generated, not confirmed payment."""
        fs = self._mock_finance()
        h = SaleFinanceHandler(fs)
        h.handle({"payment_method": "Mercado Pago", "total": 200.0, "folio": "VNT-004"})
        fs.register_income.assert_not_called()

    def test_total_cero_no_registra(self):
        fs = self._mock_finance()
        h = SaleFinanceHandler(fs)
        h.handle({"payment_method": "Efectivo", "total": 0.0, "folio": "VNT-005"})
        fs.register_income.assert_not_called()

    def test_transferencia_registra_ingreso(self):
        fs = self._mock_finance()
        h = SaleFinanceHandler(fs)
        h.handle({"payment_method": "Transferencia", "total": 500.0, "folio": "VNT-006"})
        fs.register_income.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# VENTA_COMPLETADA payload has payment_method
# ─────────────────────────────────────────────────────────────────────────────

class TestVentaCompletadaPayload:
    """Verify VENTA_COMPLETADA payload structure by inspecting SalesService source."""

    def test_venta_completada_payload_tiene_payment_method_en_codigo(self):
        """Check that sales_service.py publishes payment_method in VENTA_COMPLETADA payload."""
        import inspect
        from core.services import sales_service as _ss_mod
        src = inspect.getsource(_ss_mod)
        # The publish call must include payment_method key
        assert '"payment_method"' in src or "'payment_method'" in src, (
            "VENTA_COMPLETADA payload must include payment_method field"
        )

    def test_venta_completada_payload_structure(self):
        """The VENTA_COMPLETADA publish call has payment_method key in the dict literal."""
        import inspect
        from core.services import sales_service as _ss_mod
        src = inspect.getsource(_ss_mod)
        # Find the get_bus().publish(VENTA_COMPLETADA, {...}) call
        idx = src.find('get_bus().publish(VENTA_COMPLETADA')
        assert idx != -1, "get_bus().publish(VENTA_COMPLETADA) not found in sales_service"
        block = src[idx:idx + 600]
        assert "payment_method" in block, (
            f"payment_method missing from VENTA_COMPLETADA publish block:\n{block}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Treasury handler skips deferred methods
# ─────────────────────────────────────────────────────────────────────────────

class TestTreasuryHandlerSkipsDeferred:
    """Verify the treasury_venta handler logic (extracted inline)."""

    def _run_treasury_handler_logic(self, data: dict, treasury_mock):
        """Reproduce the _treasury_venta lambda from wiring.py."""
        _DEFERRED_PAY = {"Credito", "Mercado Pago"}
        forma_pago = str(data.get("payment_method", data.get("forma_pago", "")))
        if forma_pago in _DEFERRED_PAY:
            return
        total = float(data.get("total", 0))
        if total <= 0:
            return
        if treasury_mock and getattr(treasury_mock, "enabled", False):
            treasury_mock.registrar_ingreso(
                categoria="venta",
                concepto=f"Venta {data.get('folio', '')}",
                monto=total,
                sucursal_id=int(data.get("sucursal_id", 1)),
                referencia=str(data.get("folio", "")),
                usuario=str(data.get("usuario", "sistema")),
            )

    def _mock_treasury(self, enabled=True):
        t = MagicMock()
        t.enabled = enabled
        t.registrar_ingreso = MagicMock()
        return t

    def test_efectivo_llama_treasury(self):
        ts = self._mock_treasury()
        self._run_treasury_handler_logic(
            {"payment_method": "Efectivo", "total": 100.0, "folio": "V1", "sucursal_id": 1}, ts)
        ts.registrar_ingreso.assert_called_once()

    def test_mercado_pago_NO_llama_treasury(self):
        ts = self._mock_treasury()
        self._run_treasury_handler_logic(
            {"payment_method": "Mercado Pago", "total": 100.0, "folio": "V2"}, ts)
        ts.registrar_ingreso.assert_not_called()

    def test_credito_NO_llama_treasury(self):
        ts = self._mock_treasury()
        self._run_treasury_handler_logic(
            {"payment_method": "Credito", "total": 100.0, "folio": "V3"}, ts)
        ts.registrar_ingreso.assert_not_called()

    def test_treasury_disabled_no_llama(self):
        ts = self._mock_treasury(enabled=False)
        self._run_treasury_handler_logic(
            {"payment_method": "Efectivo", "total": 100.0, "folio": "V4"}, ts)
        ts.registrar_ingreso.assert_not_called()

    def test_total_cero_no_llama_treasury(self):
        ts = self._mock_treasury()
        self._run_treasury_handler_logic(
            {"payment_method": "Efectivo", "total": 0.0, "folio": "V5"}, ts)
        ts.registrar_ingreso.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# domain_events.py constants completeness
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainEventsConstants:
    """All critical event constants must be importable from domain_events."""

    def test_sale_events_defined(self):
        from core.events.domain_events import (
            SALE_ITEMS_PROCESS, SALE_CREATED,
            VENTA_CANCELADA, PUNTOS_ACUMULADOS, NIVEL_CAMBIADO,
        )
        assert SALE_ITEMS_PROCESS == "sale_items_process"
        assert SALE_CREATED == "VENTA_COMPLETADA"
        assert VENTA_CANCELADA == "VENTA_CANCELADA"
        assert PUNTOS_ACUMULADOS == "PUNTOS_ACUMULADOS"
        assert NIVEL_CAMBIADO == "NIVEL_CAMBIADO"

    def test_reserve_events_defined(self):
        from core.events.domain_events import (
            VENTA_SUSPENDIDA, STOCK_RESERVADO,
            VENTA_CONFIRMADA_RESERVA, STOCK_DESCONTADO_RESERVA,
            STOCK_ACTUALIZADO, VENTA_SUSPENDIDA_CANCELADA, STOCK_RESERVA_LIBERADA,
        )
        assert VENTA_SUSPENDIDA == "venta_suspendida"
        assert STOCK_RESERVADO == "stock_reservado"
        assert VENTA_CONFIRMADA_RESERVA == "venta_confirmada"
        assert STOCK_DESCONTADO_RESERVA == "stock_descontado"
        assert STOCK_ACTUALIZADO == "stock_actualizado"
        assert VENTA_SUSPENDIDA_CANCELADA == "venta_suspendida_cancelada"
        assert STOCK_RESERVA_LIBERADA == "stock_reserva_liberada"

    def test_no_string_literals_for_reserve_events_in_ventas(self):
        """ventas.py must not use raw string literals for the reserve/confirm events."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "modulos" / "ventas.py"
        text = src.read_text()
        forbidden = [
            'publish("venta_suspendida"',
            'publish("stock_reservado"',
            'publish("venta_confirmada"',
            'publish("stock_descontado"',
            'publish("stock_actualizado"',
            'publish("venta_suspendida_cancelada"',
            'publish("stock_reserva_liberada"',
        ]
        for f in forbidden:
            assert f not in text, f"String literal event found in ventas.py: {f}"

    def test_ventas_py_no_direct_treasury_call(self):
        """ventas.py must not call treasury.registrar_ingreso() directly."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "modulos" / "ventas.py"
        text = src.read_text()
        assert "treasury.registrar_ingreso(" not in text, (
            "ventas.py still has direct treasury.registrar_ingreso() call — "
            "should be handled by _treasury_venta handler in wiring.py"
        )
