import os
import sys
import json
import asyncio
import importlib.util as _ilu
from types import SimpleNamespace
from unittest.mock import AsyncMock


_HERE = os.path.dirname(os.path.abspath(__file__))
_WA_ROOT = os.path.abspath(os.path.join(_HERE, "../../whatsapp_service"))
for _k in list(sys.modules.keys()):
    if _k == "config" or _k.startswith("config."):
        del sys.modules[_k]
if _WA_ROOT not in sys.path:
    sys.path.insert(0, _WA_ROOT)

_cfg_spec = _ilu.spec_from_file_location("config", os.path.join(_WA_ROOT, "config", "__init__.py"))
_cfg_mod = _ilu.module_from_spec(_cfg_spec); sys.modules["config"] = _cfg_mod; _cfg_spec.loader.exec_module(_cfg_mod)
_set_spec = _ilu.spec_from_file_location("config.settings", os.path.join(_WA_ROOT, "config", "settings.py"))
_set_mod = _ilu.module_from_spec(_set_spec); sys.modules["config.settings"] = _set_mod; _set_spec.loader.exec_module(_set_mod)
_cfg_mod.settings = _set_mod


def _run(coro):
    return asyncio.run(coro)


def _text_payload(from_number="5215550001111", msg_id="m1", body="hola"):
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "pn-1"},
                    "messages": [{
                        "id": msg_id,
                        "from": from_number,
                        "timestamp": "1700000000",
                        "type": "text",
                        "text": {"body": body},
                    }]
                }
            }]
        }]
    }


class _Req:
    def __init__(self, payload: dict, headers=None):
        self._body = json.dumps(payload).encode("utf-8")
        self.headers = headers or {}
        self.client = SimpleNamespace(host="127.0.0.1")

    async def body(self):
        return self._body


def test_webhook_invalid_signature_returns_403(monkeypatch):
    import webhook.whatsapp as wh
    monkeypatch.setattr("config.settings.WA_APP_SECRET", "secret", raising=False)
    monkeypatch.setattr(wh, "verify_signature", lambda *_args, **_kwargs: False)
    req = _Req(_text_payload(), headers={"X-Hub-Signature-256": "sha256=bad"})
    resp = _run(wh.receive_message(req))
    assert getattr(resp, "status_code", None) == 403


def test_webhook_status_update_is_ignored():
    import webhook.whatsapp as wh
    req = _Req({"entry": [{"changes": [{"value": {"statuses": [{"id": "x", "status": "read"}]}}]}]})
    out = _run(wh.receive_message(req))
    assert out["status"] == "ok"


def test_webhook_group_message_is_ignored():
    import webhook.whatsapp as wh
    req = _Req(_text_payload(from_number="12036300@g.us"))
    out = _run(wh.receive_message(req))
    assert out["status"] == "ok"


def test_webhook_rate_limit_blocks_processing(monkeypatch):
    import webhook.whatsapp as wh
    wh._conversation_store = SimpleNamespace(
        is_duplicate=lambda _mid: False,
        log_message=lambda *_args, **_kwargs: None,
    )
    wh._number_router = SimpleNamespace(route=lambda _msg: SimpleNamespace())
    called = {"n": 0}

    async def _route(_msg, _cfg):
        called["n"] += 1
    wh._message_router = SimpleNamespace(route=_route)
    monkeypatch.setattr(wh, "_rate_limiter", SimpleNamespace(is_allowed=lambda _phone: False))

    req = _Req(_text_payload(msg_id="m2"))
    out = _run(wh.receive_message(req))
    assert out["status"] == "ok"
    assert called["n"] == 0


def test_sender_fails_without_credentials(monkeypatch):
    import messaging.sender as sender
    monkeypatch.setattr(sender, "_get_whatsapp_config", lambda _sid=None: (_ for _ in ()).throw(ValueError("no config")))
    ok = _run(sender.send_text("+5215550001111", "hola"))
    assert ok is False
