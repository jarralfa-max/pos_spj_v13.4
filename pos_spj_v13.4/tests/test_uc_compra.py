# tests/test_uc_compra.py — SPJ POS v13.5
"""
Tests unitarios para ProcesarCompraUC.
Todas las dependencias se mockean para aislar el UC.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, call

from core.use_cases.compra import (
    ProcesarCompraUC, ItemCompra, DatosCompra, ResultadoCompra,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_uc(purchase_ok=True, purchase_side_effect=None):
    """Construye un UC con mocks configurables."""
    purchase_svc = MagicMock()
    if purchase_side_effect:
        purchase_svc.register_purchase.side_effect = purchase_side_effect
    else:
        purchase_svc.register_purchase.return_value = "COMP-001"
    # db.execute chain para recuperar compra_id
    row_mock = MagicMock()
    row_mock.__getitem__ = lambda self, i: 42
    purchase_svc.db.execute.return_value.fetchone.return_value = row_mock

    finance_svc = MagicMock()
    finance_svc.registrar_asiento.return_value = 99
    finance_svc.crear_cxp.return_value = 7

    inv_svc  = MagicMock()
    event_bus = MagicMock()

    uc = ProcesarCompraUC(
        purchase_service  = purchase_svc,
        finance_service   = finance_svc,
        inventory_service = inv_svc,
        event_bus         = event_bus,
    )
    return uc, purchase_svc, finance_svc, inv_svc, event_bus


def _items():
    return [ItemCompra(producto_id=1, nombre="Pechuga", cantidad=10.0, costo_unit=80.0)]


def _datos_contado():
    return DatosCompra(proveedor_id=5, forma_pago="CONTADO", monto_pagado=800.0)


def _datos_credito():
    return DatosCompra(proveedor_id=5, forma_pago="CREDITO", monto_pagado=0.0)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestProcesarCompraUC:

    def test_compra_exitosa_contado_retorna_ok(self):
        uc, *_ = _make_uc()
        res = uc.ejecutar(_items(), _datos_contado(), sucursal_id=1, usuario="admin")
        assert res.ok is True
        assert res.folio == "COMP-001"
        assert res.total == 800.0

    def test_compra_credito_crea_cxp(self):
        uc, purchase_svc, finance_svc, *_ = _make_uc()
        res = uc.ejecutar(_items(), _datos_credito(), sucursal_id=1, usuario="admin")
        assert res.ok is True
        finance_svc.crear_cxp.assert_called_once()
        kwargs = finance_svc.crear_cxp.call_args
        assert kwargs.kwargs.get("amount") == 800.0 or (
            len(kwargs.args) >= 3 and kwargs.args[2] == 800.0
        )

    def test_asiento_inventario_1201_2101_siempre_registrado(self):
        uc, _, finance_svc, *_ = _make_uc()
        uc.ejecutar(_items(), _datos_contado(), sucursal_id=1, usuario="admin")
        calls = finance_svc.registrar_asiento.call_args_list
        inventario_call = next(
            (c for c in calls
             if c.kwargs.get("debe") == "1201" or (c.args and c.args[0] == "1201")),
            None,
        )
        assert inventario_call is not None, "Asiento 1201/2101 no fue llamado"

    def test_asiento_pago_contado_solo_en_contado(self):
        uc, _, finance_svc, *_ = _make_uc()
        # Crédito: asiento de pago NO debe llamarse
        uc.ejecutar(_items(), _datos_credito(), sucursal_id=1, usuario="admin")
        calls = finance_svc.registrar_asiento.call_args_list
        pago_calls = [
            c for c in calls
            if c.kwargs.get("evento") == "PAGO_COMPRA_CONTADO"
            or (c.kwargs.get("debe") == "2101" and c.kwargs.get("haber") == "1101")
        ]
        assert len(pago_calls) == 0, "Asiento de pago contado no debe registrarse en CREDITO"

    def test_items_vacios_retorna_error(self):
        uc, *_ = _make_uc()
        res = uc.ejecutar([], _datos_contado(), sucursal_id=1, usuario="admin")
        assert res.ok is False
        assert "items" in res.error.lower() or "vacío" in res.error.lower() or "item" in res.error.lower()

    def test_fallo_purchase_service_retorna_error(self):
        uc, *_ = _make_uc(purchase_side_effect=RuntimeError("DB locked"))
        res = uc.ejecutar(_items(), _datos_contado(), sucursal_id=1, usuario="admin")
        assert res.ok is False
        assert "DB locked" in res.error

    def test_compra_publica_evento_bus(self):
        uc, _, _, _, event_bus = _make_uc()
        uc.ejecutar(_items(), _datos_contado(), sucursal_id=1, usuario="admin")
        event_bus.publish.assert_called_once()
        payload = event_bus.publish.call_args[0][1]
        assert payload["folio"] == "COMP-001"

    def test_fallo_asiento_no_bloquea_compra(self):
        uc, _, finance_svc, *_ = _make_uc()
        finance_svc.registrar_asiento.side_effect = Exception("tabla no existe")
        res = uc.ejecutar(_items(), _datos_contado(), sucursal_id=1, usuario="admin")
        # Compra registrada correctamente aunque el asiento falle
        assert res.ok is True
        assert res.folio == "COMP-001"
