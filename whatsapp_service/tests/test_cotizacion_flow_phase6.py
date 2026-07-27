import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if "config" in sys.modules and not hasattr(sys.modules["config"], "__path__"):
    del sys.modules["config"]

from flows.cotizacion_flow import CotizacionFlow
from models.context import ConversationContext, FlowState, PedidoItem


class DummyIntent:
    def __init__(self, action_id="", number=0):
        self.action_id = action_id
        self.number = number


async def _run(flow, ctx, action_id):
    return await flow.handle(ctx, DummyIntent(action_id=action_id))


def _mk_flow():
    erp = MagicMock()
    erp.get_categorias.return_value = ["pollo"]
    erp.db = MagicMock()
    events = MagicMock()
    flow = CotizacionFlow(erp=erp, events=events)
    flow.orchestrator = MagicMock()
    return flow, erp, events


def test_quote_accept_converts_to_sale_and_resets_context(monkeypatch):
    flow, erp, _events = _mk_flow()
    flow.orchestrator.convertir_cotizacion_a_venta.return_value = {"folio": "WA-VENTA-1", "total": 120.0}

    ctx = ConversationContext(phone="52155", state=FlowState.COTIZACION_CONFIRMACION)
    ctx.current_quote_id = 5
    ctx.current_quote_folio = "COT-5"
    ctx.cliente_id = 10

    monkeypatch.setattr("flows.cotizacion_flow.send_text", AsyncMock())
    monkeypatch.setattr("flows.cotizacion_flow.interactive.send_menu_principal", AsyncMock())

    import asyncio
    result = asyncio.run(_run(flow, ctx, "quote_accept"))

    assert result.new_state == FlowState.IDLE
    flow.orchestrator.convertir_cotizacion_a_venta.assert_called_once_with(cotizacion_id=5, cliente_id=10)
    assert ctx.current_quote_id is None
    assert ctx.current_quote_folio == ""


def test_quote_reject_marks_rejected_and_emits_event(monkeypatch):
    flow, erp, events = _mk_flow()
    ctx = ConversationContext(phone="52155", state=FlowState.COTIZACION_CONFIRMACION)
    ctx.current_quote_id = 7
    ctx.current_quote_folio = "COT-7"
    ctx.cliente_id = 10
    ctx.sucursal_id = 2

    monkeypatch.setattr("flows.cotizacion_flow.send_text", AsyncMock())
    monkeypatch.setattr("flows.cotizacion_flow.interactive.send_menu_principal", AsyncMock())

    import asyncio
    result = asyncio.run(_run(flow, ctx, "quote_reject"))

    assert result.new_state == FlowState.IDLE
    erp.db.execute.assert_called_with("UPDATE cotizaciones SET estado='rechazada' WHERE id=?", (7,))
    assert events.emit.called


def test_quote_accept_without_orchestrator_emits_canonical_events(monkeypatch):
    flow, erp, events = _mk_flow()
    flow.orchestrator = None
    erp.convertir_cotizacion_a_venta.return_value = {"venta_id": 55, "folio": "VTA-55", "total": 210.0}

    ctx = ConversationContext(phone="52155", state=FlowState.COTIZACION_CONFIRMACION)
    ctx.current_quote_id = 9
    ctx.current_quote_folio = "COT-9"
    ctx.cliente_id = 88
    ctx.sucursal_id = 2

    monkeypatch.setattr("flows.cotizacion_flow.send_text", AsyncMock())
    monkeypatch.setattr("flows.cotizacion_flow.interactive.send_menu_principal", AsyncMock())

    import asyncio
    result = asyncio.run(_run(flow, ctx, "quote_accept"))

    assert result.new_state == FlowState.IDLE
    emitted = [c.args[0] for c in events.emit.call_args_list]
    assert "WHATSAPP_QUOTE_ACCEPTED" in emitted
    assert "WHATSAPP_QUOTE_CONVERTED_TO_SALE" in emitted
