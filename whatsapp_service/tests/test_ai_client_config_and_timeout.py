import asyncio

from ai.intent_ai_client import CloudIntentAIClient


class FakeDB:
    def __init__(self, cfg):
        self.cfg = cfg

    def execute(self, sql, params=()):
        class R:
            def __init__(self, row): self._row = row
            def fetchone(self): return self._row
        if "SELECT valor FROM configuraciones" in sql:
            key = params[0]
            return R((self.cfg.get(key, ""),))
        return R(None)


def test_config_priority_erp_over_env(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "env-provider")
    db = FakeDB({"ai_provider": "erp-provider"})
    client = CloudIntentAIClient(db=db)
    assert client._cfg("ai_provider", "mock") == "erp-provider"


def test_timeout_returns_controlled_error():
    db = FakeDB({"ai_timeout_seconds": "0"})
    client = CloudIntentAIClient(db=db)
    out = asyncio.run(client.parse({"message": "quiero pollo"}))
    assert out.ok is False
    assert out.error
