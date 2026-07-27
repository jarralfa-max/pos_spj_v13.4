import asyncio
from models.message import IncomingMessage, MessageType
from models.context import ConversationContext
from parser.intent_parser import ParsedIntent
from ai.intent_resolver import IntentResolver


class DummyParser:
    async def parse(self, msg):
        return ParsedIntent(intent="pedido", confidence=0.8, source="regex")


class FakeDB:
    def __init__(self, cfg):
        self.cfg = cfg
    def execute(self, sql, params=()):
        class R:
            def __init__(self, row): self._row = row
            def fetchone(self): return self._row
        key = params[0] if params else ""
        if "SELECT valor FROM configuraciones" in sql:
            return R((self.cfg.get(key, ""),))
        return R(None)
    def commit(self):
        return None


def mk_msg(text="quiero pechuga"):
    from datetime import datetime
    return IncomingMessage(message_id="1", from_number="521111", phone_number_id="x", timestamp=datetime.now(), type=MessageType.TEXT, text=text)


def test_ai_disabled_uses_local_parser():
    db = FakeDB({"ai_intent_enabled": "0"})
    r = IntentResolver(parser=DummyParser(), db=db)
    out = asyncio.run(r.resolve(mk_msg(), ConversationContext(phone="521111")))
    assert out.intent == "pedido"
    assert out.source == "local"
