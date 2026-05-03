# tests/test_wa_orchestrator.py — SPJ POS v13.5
"""
Tests unitarios para BusinessOrchestrator.
"""
import sys, os, importlib.util as _ilu

# ── WA service sys.path setup ────────────────────────────────────────────────
_WA_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../whatsapp_service'))
for _k in list(sys.modules.keys()):
    if _k == 'config' or _k.startswith('config.'):
        del sys.modules[_k]
if _WA_ROOT not in sys.path:
    sys.path.insert(0, _WA_ROOT)
sys.path.insert(1, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Force-load the WA config package so imports find the right module
_cfg_spec = _ilu.spec_from_file_location('config', os.path.join(_WA_ROOT, 'config', '__init__.py'))
_cfg_mod = _ilu.module_from_spec(_cfg_spec); sys.modules['config'] = _cfg_mod; _cfg_spec.loader.exec_module(_cfg_mod)
_set_spec = _ilu.spec_from_file_location('config.settings', os.path.join(_WA_ROOT, 'config', 'settings.py'))
_set_mod = _ilu.module_from_spec(_set_spec); sys.modules['config.settings'] = _set_mod; _set_spec.loader.exec_module(_set_mod)
_cfg_mod.settings = _set_mod

import pytest
from unittest.mock import MagicMock


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_erp():
    erp = MagicMock()
    # _check_flag queries module_toggles
    erp.db.execute.return_value.fetchone.return_value = None
    erp.crear_cotizacion_wa.return_value = {"cotizacion_id": 1, "folio": "CWA-001", "total": 500.0}
    erp.convertir_cotizacion_a_venta.return_value = {
        "venta_id": 10, "folio": "WA-001", "total": 500.0,
        "items": [{"producto_id": 1, "nombre": "Pechuga", "cantidad": 2, "precio_unitario": 250}]
    }
    erp.requiere_anticipo.return_value = False
    erp.calcular_anticipo_rules.return_value = {"requiere": False, "monto": 0.0, "razon": ""}
    erp.registrar_anticipo.return_value = 5
    erp.crear_pedido_wa.return_value = {"venta_id": 20, "folio": "WA-002", "total": 300.0}
    erp.get_credito_disponible.return_value = 1000.0
    erp.confirmar_pago_anticipo.return_value = True
    erp.get_staff_phones.return_value = []
    erp.db.execute.return_value.fetchall.return_value = []
    return erp


@pytest.fixture
def mock_events():
    ev = MagicMock()
    ev.emit = MagicMock()
    return ev


@pytest.fixture
def orch(mock_erp, mock_events):
    from erp.business_orchestrator import BusinessOrchestrator
    o = BusinessOrchestrator.__new__(BusinessOrchestrator)
    o.erp = mock_erp
    o.events = mock_events
    o.sucursal_id = 1
    o._advanced_enabled = False  # disable stock checks for unit tests
    return o


_ITEMS = [{"producto_id": 1, "nombre": "Pechuga", "cantidad": 2, "precio_unitario": 250}]


# ── confirmar_cotizacion ──────────────────────────────────────────────────────

class TestConfirmarCotizacion:

    def test_calls_erp_crear_cotizacion(self, orch, mock_erp):
        orch.confirmar_cotizacion(1, cliente_id=5, items=_ITEMS)
        mock_erp.crear_cotizacion_wa.assert_called_once()

    def test_emits_quote_created(self, orch, mock_events):
        orch.confirmar_cotizacion(1, cliente_id=5, items=_ITEMS)
        emitted = [c.args[0] for c in mock_events.emit.call_args_list]
        from erp.events import QUOTE_CREATED
        assert QUOTE_CREATED in emitted

    def test_returns_cotizacion_result(self, orch):
        result = orch.confirmar_cotizacion(1, cliente_id=5, items=_ITEMS)
        assert result["folio"] == "CWA-001"
        assert result["total"] == 500.0


# ── convertir_cotizacion_a_venta ──────────────────────────────────────────────

class TestConvertirCotizacion:

    def test_returns_none_when_erp_returns_none(self, orch, mock_erp):
        mock_erp.convertir_cotizacion_a_venta.return_value = None
        result = orch.convertir_cotizacion_a_venta(99, cliente_id=1)
        assert result is None

    def test_emits_sale_created(self, orch, mock_events):
        orch.convertir_cotizacion_a_venta(1, cliente_id=1)
        emitted = [c.args[0] for c in mock_events.emit.call_args_list]
        from erp.events import SALE_CREATED
        assert SALE_CREATED in emitted

    def test_emits_payment_required_when_anticipo_required(self, orch, mock_erp, mock_events):
        mock_erp.calcular_anticipo_rules.return_value = {
            "requiere": True, "monto": 250.0, "razon": "sin credito"
        }
        orch.convertir_cotizacion_a_venta(1, cliente_id=1)
        emitted = [c.args[0] for c in mock_events.emit.call_args_list]
        from erp.events import PAYMENT_REQUIRED
        assert PAYMENT_REQUIRED in emitted


# ── procesar_pedido_wa ────────────────────────────────────────────────────────

class TestProcesarPedidoWA:

    def test_emits_sale_created(self, orch, mock_events):
        orch.procesar_pedido_wa(
            venta_id=20, folio="WA-002", total=300.0,
            cliente_id=1, items=_ITEMS,
        )
        emitted = [c.args[0] for c in mock_events.emit.call_args_list]
        from erp.events import SALE_CREATED
        assert SALE_CREATED in emitted

    def test_emits_anticipo_when_required(self, orch, mock_erp, mock_events):
        mock_erp.calcular_anticipo_rules.return_value = {
            "requiere": True, "monto": 150.0, "razon": ""
        }
        orch._advanced_enabled = True
        orch.procesar_pedido_wa(
            venta_id=20, folio="WA-002", total=300.0,
            cliente_id=1, items=_ITEMS,
        )
        emitted = [c.args[0] for c in mock_events.emit.call_args_list]
        from erp.events import WA_ANTICIPO_REQUERIDO
        assert WA_ANTICIPO_REQUERIDO in emitted


# ── confirmar_anticipo ────────────────────────────────────────────────────────

class TestConfirmarAnticipo:

    def test_emits_payment_received(self, orch, mock_events):
        # _get_folio queries db
        orch.erp.db.execute.return_value.fetchone.return_value = None
        orch.confirmar_anticipo(venta_id=10, monto=200.0, referencia="ref123")
        emitted = [c.args[0] for c in mock_events.emit.call_args_list]
        from erp.events import PAYMENT_RECEIVED
        assert PAYMENT_RECEIVED in emitted

    def test_returns_false_when_erp_fails(self, orch, mock_erp):
        mock_erp.confirmar_pago_anticipo.return_value = False
        result = orch.confirmar_anticipo(venta_id=10, monto=200.0)
        assert result is False
