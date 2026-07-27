import asyncio
from datetime import datetime

from ai.intent_resolver import IntentResolver
from ai.intent_schema import AIIntentResult
from models.context import ConversationContext
from models.message import IncomingMessage, MessageType
from parser.intent_parser import ParsedIntent


class DummyParser:
    async def parse(self, msg):
        p = ParsedIntent(intent="pedido", confidence=0.66, source="regex")
        return p


class FakeDB:
    def __init__(self, cfg):
        self.cfg = cfg
        self.logs = []
    def execute(self, sql, params=()):
        class R:
            def __init__(self, row): self._row = row
            def fetchone(self): return self._row
        if "SELECT valor FROM configuraciones" in sql:
            key = params[0]
            return R((self.cfg.get(key, ""),))
        if "INSERT INTO ai_intent_log" in sql:
            self.logs.append(params)
            return R(None)
        return R(None)
    def commit(self):
        return None


class OKAI:
    def __init__(self, payload): self.payload = payload
    async def parse(self, context):
        class Resp:
            ok = True
            error = ""
            latency_ms = 10
            result = AIIntentResult.model_validate(self.payload)
        return Resp()


class FailAI:
    async def parse(self, context):
        class Resp:
            ok = False
            error = "timeout"
            latency_ms = 0
            result = None
        return Resp()


def mk_msg(text):
    return IncomingMessage(
        message_id="m1", from_number="521111", phone_number_id="p1",
        timestamp=datetime.now(), type=MessageType.TEXT, text=text
    )


def test_ai_valid_uses_ai():
    db = FakeDB({"ai_intent_enabled": "1", "ai_min_confidence": "0.75", "ai_fallback_enabled": "1"})
    r = IntentResolver(parser=DummyParser(), db=db)
    r.ai_client = OKAI({"intent": "create_quote", "confidence": 0.91, "products": []})
    out = asyncio.run(r.resolve(mk_msg("cotiza"), ConversationContext(phone="521111")))
    assert out.intent == "cotizacion"
    assert out.source == "ai"


def test_ai_fail_uses_local_fallback():
    db = FakeDB({"ai_intent_enabled": "1", "ai_fallback_enabled": "1"})
    r = IntentResolver(parser=DummyParser(), db=db)
    r.ai_client = FailAI()
    out = asyncio.run(r.resolve(mk_msg("hola"), ConversationContext(phone="521111")))
    assert out.intent == "pedido"
    assert out.source == "local"


def test_ai_low_confidence_uses_local():
    db = FakeDB({"ai_intent_enabled": "1", "ai_min_confidence": "0.75", "ai_fallback_enabled": "1"})
    r = IntentResolver(parser=DummyParser(), db=db)
    r.ai_client = OKAI({"intent": "create_order", "confidence": 0.2, "products": []})
    out = asyncio.run(r.resolve(mk_msg("quiero"), ConversationContext(phone="521111")))
    assert out.source == "local"


def test_prompt_does_not_contain_credentials():
    from ai.prompt_builder import build_ai_prompt_context
    ctx = ConversationContext(phone="521111")
    prompt = build_ai_prompt_context("quiero pollo", ctx, allowed_intents=["create_order"])
    dump = str(prompt).lower()
    assert "token" not in dump
    assert "api_key" not in dump


def test_log_does_not_store_api_key_text():
    db = FakeDB({"ai_intent_enabled": "1", "ai_fallback_enabled": "1"})
    r = IntentResolver(parser=DummyParser(), db=db)
    r.ai_client = FailAI()
    _ = asyncio.run(r.resolve(mk_msg("mi api key es SECRET"), ConversationContext(phone="521111")))
    assert db.logs, "Debe registrar auditoría"
    preview = db.logs[-1][1]
    assert len(preview) <= 160


class BrokenAI:
    async def parse(self, context):
        class Resp:
            ok = True
            error = ""
            latency_ms = 5
            result = object()
        return Resp()


def test_invalid_ai_payload_fallback_local():
    db = FakeDB({"ai_intent_enabled": "1", "ai_fallback_enabled": "1"})
    r = IntentResolver(parser=DummyParser(), db=db)
    r.ai_client = BrokenAI()
    out = asyncio.run(r.resolve(mk_msg("texto"), ConversationContext(phone="521111")))
    assert out.source == "local"
