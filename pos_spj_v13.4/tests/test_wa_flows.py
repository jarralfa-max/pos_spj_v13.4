# tests/test_wa_flows.py — SPJ POS v13.5
"""
Tests para los flows de WhatsApp (state machine).
Mockea ERPBridge, WAEventEmitter y los helpers de mensajería.
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
# Stub optional heavy deps not installed in test environment
from unittest.mock import MagicMock as _MM
for _dep in ('httpx', 'ollama', 'aiohttp'):
    if _dep not in sys.modules:
        sys.modules[_dep] = _MM()

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ctx(state="idle", phone="5551234567", sucursal_id=1):
    from models.context import ConversationContext, FlowState, PedidoItem
    ctx = ConversationContext.__new__(ConversationContext)
    ctx.phone = phone
    ctx.sucursal_id = sucursal_id
    ctx.state = FlowState(state)
    ctx.pedido_items = []
    ctx.cotizacion_items = []
    ctx.current_product = None
    ctx.pending_folio = None
    ctx.cliente_id = 1
    ctx.cliente_nombre = "Test"
    ctx.tipo_entrega = None
    ctx.direccion = ""
    ctx.fecha_entrega = ""
    ctx.notas = ""
    ctx.nombre_registro = ""
    return ctx


def _make_intent(intent="menu_action", action_id="", confidence=1.0,
                 number=0.0, products=None, text=""):
    from parser.intent_parser import ParsedIntent
    return ParsedIntent(
        intent=intent, confidence=confidence,
        action_id=action_id, products=products or [],
        number=number, raw_text=text, source="button",
    )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def mock_erp():
    erp = MagicMock()
    erp.get_categorias.return_value = ["Carne", "Cerdo"]
    erp.get_productos_by_category.return_value = [
        {"id": 1, "nombre": "Pechuga", "precio": 95.0,
         "stock": 10.0, "unidad": "kg", "categoria": "Carne"}
    ]
    erp.get_producto.return_value = {
        "id": 1, "nombre": "Pechuga", "precio": 95.0,
        "stock": 10.0, "unidad": "kg", "categoria": "Carne"
    }
    erp.crear_pedido_wa.return_value = {"venta_id": 1, "folio": "WA-001", "total": 190.0}
    erp.crear_cotizacion_wa.return_value = {"cotizacion_id": 2, "folio": "CWA-001", "total": 190.0}
    erp.requiere_anticipo.return_value = False
    return erp


@pytest.fixture
def mock_events():
    ev = MagicMock()
    ev.emit = MagicMock()
    return ev


# ── Mock messaging helpers ────────────────────────────────────────────────────

def _mock_interactive():
    """Mock all interactive messaging calls."""
    import messaging
    import messaging.interactive as mi
    import messaging.sender as ms
    mi.send_main_menu = AsyncMock()
    mi.send_categorias = AsyncMock()
    mi.send_productos = AsyncMock()
    mi.send_interactive_buttons = AsyncMock()
    mi.send_interactive_list = AsyncMock()
    ms.send_text = AsyncMock()
    return mi, ms


# ── MenuFlow Tests ────────────────────────────────────────────────────────────

class TestMenuFlow:

    def test_menu_flow_instantiates(self, mock_erp, mock_events):
        from flows.menu_flow import MenuFlow
        flow = MenuFlow(erp=mock_erp, events=mock_events)
        assert flow is not None

    def test_menu_flow_handles_idle_state(self, mock_erp, mock_events):
        import messaging
        import messaging.interactive as mi
        import messaging.sender as ms
        mi.send_main_menu = AsyncMock()
        ms.send_text = AsyncMock()
        from flows.menu_flow import MenuFlow
        flow = MenuFlow(erp=mock_erp, events=mock_events)
        ctx = _make_ctx("idle")
        intent = _make_intent("greeting")
        result = _run(flow.handle(ctx, intent))
        assert result is not None

    def test_menu_flow_handles_menu_action(self, mock_erp, mock_events):
        import messaging.interactive as mi
        import messaging.sender as ms
        mi.send_main_menu = AsyncMock()
        mi.send_categorias = AsyncMock()
        ms.send_text = AsyncMock()
        from flows.menu_flow import MenuFlow
        flow = MenuFlow(erp=mock_erp, events=mock_events)
        ctx = _make_ctx("idle")
        intent = _make_intent("menu_action", action_id="menu_pedido")
        result = _run(flow.handle(ctx, intent))
        assert result is not None


# ── PedidoFlow Tests ──────────────────────────────────────────────────────────

class TestPedidoFlow:

    def test_pedido_flow_instantiates(self, mock_erp, mock_events):
        from flows.pedido_flow import PedidoFlow
        flow = PedidoFlow(erp=mock_erp, events=mock_events)
        assert flow is not None

    def test_categoria_state_fetches_products(self, mock_erp, mock_events):
        import messaging.interactive as mi
        import messaging.sender as ms
        mi.send_productos = AsyncMock()
        mi.send_categorias = AsyncMock()
        ms.send_text = AsyncMock()
        from flows.pedido_flow import PedidoFlow
        flow = PedidoFlow(erp=mock_erp, events=mock_events)
        ctx = _make_ctx("pedido_categoria")
        intent = _make_intent("select_category", action_id="cat_carne")
        _run(flow.handle(ctx, intent))
        mock_erp.get_productos_by_category.assert_called()

    def test_confirmacion_state_calls_crear_pedido(self, mock_erp, mock_events):
        import messaging.interactive as mi
        import messaging.sender as ms
        mi.send_interactive_buttons = AsyncMock()
        mi.send_confirmacion_pedido = AsyncMock()
        mi.send_menu_principal = AsyncMock()
        ms.send_text = AsyncMock()
        from flows.pedido_flow import PedidoFlow
        from models.context import PedidoItem
        flow = PedidoFlow(erp=mock_erp, events=mock_events)
        ctx = _make_ctx("pedido_confirmacion")
        ctx.pedido_items = [
            PedidoItem(producto_id=1, nombre="Pechuga", cantidad=2.0,
                       unidad="kg", precio_unitario=95.0)
        ]
        ctx.tipo_entrega = "sucursal"
        # The flow checks action_id == "confirm_pedido"
        intent = _make_intent("confirm", action_id="confirm_pedido")
        _run(flow.handle(ctx, intent))
        mock_erp.crear_pedido_wa.assert_called()

    def test_unhandled_state_returns_result(self, mock_erp, mock_events):
        from flows.pedido_flow import PedidoFlow
        flow = PedidoFlow(erp=mock_erp, events=mock_events)
        # PedidoFlow handles IDLE — use a state it doesn't handle
        ctx = _make_ctx("pago_metodo")
        result = _run(flow.handle(ctx, _make_intent("unknown")))
        assert result is not None
        assert result.handled is False


# ── CotizacionFlow Tests ──────────────────────────────────────────────────────

class TestCotizacionFlow:

    def test_cotizacion_flow_instantiates(self, mock_erp, mock_events):
        from flows.cotizacion_flow import CotizacionFlow
        flow = CotizacionFlow(erp=mock_erp, events=mock_events)
        assert flow is not None

    def test_confirmacion_calls_crear_cotizacion(self, mock_erp, mock_events):
        import messaging.interactive as mi
        import messaging.sender as ms
        mi.send_interactive_buttons = AsyncMock()
        mi.send_menu_principal = AsyncMock()
        ms.send_text = AsyncMock()
        from flows.cotizacion_flow import CotizacionFlow
        from models.context import PedidoItem
        flow = CotizacionFlow(erp=mock_erp, events=mock_events)
        ctx = _make_ctx("cotizacion_confirmacion")
        ctx.cotizacion_items = [
            PedidoItem(producto_id=1, nombre="Pechuga", cantidad=2.0,
                       unidad="kg", precio_unitario=95.0)
        ]
        # The flow checks action_id == "confirm_cotizacion"
        intent = _make_intent("confirm", action_id="confirm_cotizacion")
        _run(flow.handle(ctx, intent))
        mock_erp.crear_cotizacion_wa.assert_called()


# ── PagoFlow Tests ────────────────────────────────────────────────────────────

class TestPagoFlow:

    def test_pago_flow_instantiates(self, mock_erp, mock_events):
        from flows.pago_flow import PagoFlow
        flow = PagoFlow(erp=mock_erp, events=mock_events)
        assert flow is not None

    def test_pago_flow_handles_method_selection(self, mock_erp, mock_events):
        import messaging.interactive as mi
        import messaging.sender as ms
        mi.send_interactive_buttons = AsyncMock()
        ms.send_text = AsyncMock()
        from flows.pago_flow import PagoFlow
        flow = PagoFlow(erp=mock_erp, events=mock_events)
        ctx = _make_ctx("pago_metodo")
        ctx.pending_folio = "WA-001"
        intent = _make_intent("select_pago", action_id="pago_efectivo")
        result = _run(flow.handle(ctx, intent))
        assert result is not None
