import asyncio
from types import SimpleNamespace

from router.message_router import MessageRouter
from models.context import ConversationContext, FlowState
from parser.intent_parser import ParsedIntent


class DummyStore:
    def __init__(self, ctx):
        self.ctx = ctx

    def get(self, _phone):
        return self.ctx

    def save(self, ctx):
        self.ctx = ctx


class DummyERP:
    def __init__(self):
        self.db = None

    def get_sucursales(self):
        return [{"id": 1, "nombre": "Centro"}]

    def find_cliente_by_phone(self, _phone):
        return {"id": 10, "nombre": "Cliente"}


class DummyParser:
    async def parse(self, _msg):
        return ParsedIntent(intent="pedido", confidence=0.5, source="regex")


class DummySchedules:
    def esta_abierta(self, _sid):
        return True


class DummyFlow:
    async def handle(self, ctx, intent):
        return SimpleNamespace(new_state=ctx.state, handled=True)


class FakeResolver:
    def __init__(self, intent_name):
        self.intent_name = intent_name

    async def resolve(self, msg, ctx):
        return ParsedIntent(intent=self.intent_name, confidence=0.9, source="ai")


def _build_router(intent_name: str):
    ctx = ConversationContext(phone="5512345678")
    store = DummyStore(ctx)
    router = MessageRouter(
        erp=DummyERP(),
        store=store,
        parser=DummyParser(),
        events=SimpleNamespace(),
        schedules=DummySchedules(),
        handoff=SimpleNamespace(),
    )
    router.intent_resolver = FakeResolver(intent_name)
    router.sucursal_flow = DummyFlow()
    router.registro_flow = DummyFlow()
    router.menu_flow = DummyFlow()
    router.pedido_flow = DummyFlow()
    router.repetir_flow = DummyFlow()
    router.cotizacion_flow = DummyFlow()
    router.pago_flow = DummyFlow()
    return router, store


def test_router_uses_intent_resolver_output_for_flow_routing():
    router, store = _build_router("cotizacion")
    msg = SimpleNamespace(from_number="5512345678", timestamp=None, text="cotiza 5 pollos")
    numero_cfg = SimpleNamespace(tipo=SimpleNamespace(value="sucursal"), es_global=False, sucursal_id=1, sucursal_nombre="Centro")
    asyncio.run(router.route(msg, numero_cfg))
    assert store.ctx.state == FlowState.COTIZACION_ARMANDO


def test_router_keeps_branch_selection_behavior_with_resolver():
    router, store = _build_router("sucursal")
    store.ctx.sucursal_id = 1
    store.ctx.sucursal_nombre = "Centro"

    sent = []

    async def fake_text(phone, text):
        sent.append(("text", phone, text))

    async def fake_select(phone, sucursales):
        sent.append(("select", phone, len(sucursales)))

    import router.message_router as mr
    old_text = mr.interactive.send_text
    old_sel = mr.interactive.send_seleccion_sucursal
    mr.interactive.send_text = fake_text
    mr.interactive.send_seleccion_sucursal = fake_select
    try:
        msg = SimpleNamespace(from_number="5512345678", timestamp=None, text="cambiar sucursal")
        numero_cfg = SimpleNamespace(tipo=SimpleNamespace(value="global"), es_global=True, sucursal_id=None, sucursal_nombre="")
        asyncio.run(router.route(msg, numero_cfg))
    finally:
        mr.interactive.send_text = old_text
        mr.interactive.send_seleccion_sucursal = old_sel

    assert store.ctx.state == FlowState.SELECTING_BRANCH
    assert any(x[0] == "select" for x in sent)
