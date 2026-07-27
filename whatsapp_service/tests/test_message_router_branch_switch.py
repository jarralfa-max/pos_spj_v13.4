import asyncio
from types import SimpleNamespace

from router.message_router import MessageRouter
from models.context import ConversationContext, FlowState


class DummyStore:
    def __init__(self, ctx):
        self.ctx = ctx
        self.saved = 0

    def get(self, _phone):
        return self.ctx

    def save(self, ctx):
        self.ctx = ctx
        self.saved += 1


class DummyERP:
    def __init__(self):
        self.db = None

    def get_sucursales(self):
        return [{"id": 1, "nombre": "Centro"}, {"id": 2, "nombre": "Norte"}]

    def find_cliente_by_phone(self, _phone):
        return {"id": 10, "nombre": "Cliente"}


class DummyParser:
    async def parse(self, _msg):
        return SimpleNamespace(intent="sucursal", action_id="", raw_text="cambiar sucursal")


class DummySchedules:
    def esta_abierta(self, _sid):
        return True


class DummyFlow:
    async def handle(self, ctx, intent):
        return SimpleNamespace(new_state=ctx.state, handled=True)


async def _route_once(ctx):
    store = DummyStore(ctx)
    router = MessageRouter(
        erp=DummyERP(),
        store=store,
        parser=DummyParser(),
        events=SimpleNamespace(),
        schedules=DummySchedules(),
        handoff=SimpleNamespace(),
    )
    router.sucursal_flow = DummyFlow()
    router.registro_flow = DummyFlow()
    router.menu_flow = DummyFlow()
    router.pedido_flow = DummyFlow()
    router.repetir_flow = DummyFlow()
    router.cotizacion_flow = DummyFlow()
    router.pago_flow = DummyFlow()

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
        await router.route(msg, numero_cfg)
    finally:
        mr.interactive.send_text = old_text
        mr.interactive.send_seleccion_sucursal = old_sel

    return store, sent


def test_global_number_allows_branch_change_command():
    ctx = ConversationContext(phone="5512345678")
    ctx.sucursal_id = 1
    ctx.sucursal_nombre = "Centro"
    store, sent = asyncio.run(_route_once(ctx))

    assert store.ctx.state == FlowState.SELECTING_BRANCH
    assert any(x[0] == "text" for x in sent)
    assert any(x[0] == "select" for x in sent)
