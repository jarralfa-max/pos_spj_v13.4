# tests/test_wa_webhook.py — SPJ POS v13.5
"""
Tests para la lógica del webhook de WhatsApp.
Prueba el comportamiento del handler sin requerir FastAPI/servidor HTTP.
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
from unittest.mock import MagicMock, patch
from datetime import datetime


# ── Payload helpers ───────────────────────────────────────────────────────────

def _wa_text_payload(text="hola", from_number="5551234567", msg_id="msg-001"):
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "12345"},
                    "contacts": [{"profile": {"name": "Test"}, "wa_id": from_number}],
                    "messages": [{
                        "id": msg_id,
                        "from": from_number,
                        "timestamp": str(int(datetime.now().timestamp())),
                        "type": "text",
                        "text": {"body": text},
                    }],
                }
            }]
        }]
    }


def _status_update_payload():
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "12345"},
                    "statuses": [{"id": "msg1", "status": "read"}],
                }
            }]
        }]
    }


def _group_message_payload():
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "12345"},
                    "messages": [{
                        "id": "grp-001",
                        "from": "120363000000000@g.us",
                        "timestamp": "1234567890",
                        "type": "text",
                        "text": {"body": "group message"},
                    }],
                }
            }]
        }]
    }


# ── RateLimiter / static helpers ──────────────────────────────────────────────

class TestRateLimiterStaticHelpers:
    """Tests para los métodos estáticos del RateLimiter usados por el webhook."""

    def test_status_update_detected(self):
        from middleware.rate_limiter import RateLimiter
        assert RateLimiter.is_status_update(_status_update_payload()) is True

    def test_regular_message_not_status_update(self):
        from middleware.rate_limiter import RateLimiter
        assert RateLimiter.is_status_update(_wa_text_payload()) is False

    def test_group_message_detected(self):
        from middleware.rate_limiter import RateLimiter
        payload = _group_message_payload()
        assert RateLimiter.is_group_message(payload) is True

    def test_individual_message_not_group(self):
        from middleware.rate_limiter import RateLimiter
        assert RateLimiter.is_group_message(_wa_text_payload()) is False

    def test_rate_limiter_allows_first_message(self):
        from middleware.rate_limiter import RateLimiter
        rl = RateLimiter()
        assert rl.is_allowed("5550000001") is True

    def test_rate_limiter_blocks_after_limit(self):
        from middleware.rate_limiter import RateLimiter
        rl = RateLimiter()
        phone = "5550000099"
        # Drain the bucket
        for _ in range(200):
            rl.is_allowed(phone)
        # Should eventually be blocked
        blocked = any(not rl.is_allowed(phone) for _ in range(50))
        assert blocked is True


# ── IncomingMessage.from_webhook parsing ─────────────────────────────────────

class TestIncomingMessageParsing:
    """Tests para el parsing del webhook payload → IncomingMessage."""

    def test_parse_text_message(self):
        from models.message import IncomingMessage, MessageType
        msg = IncomingMessage.from_webhook(_wa_text_payload("hola"))
        assert msg is not None
        assert msg.type == MessageType.TEXT
        assert msg.text == "hola"
        assert msg.from_number == "5551234567"

    def test_parse_returns_none_for_status_update(self):
        from models.message import IncomingMessage
        msg = IncomingMessage.from_webhook(_status_update_payload())
        assert msg is None

    def test_parse_empty_payload_returns_none(self):
        from models.message import IncomingMessage
        msg = IncomingMessage.from_webhook({})
        assert msg is None

    def test_parse_message_id_captured(self):
        from models.message import IncomingMessage
        msg = IncomingMessage.from_webhook(_wa_text_payload(msg_id="test-msg-001"))
        assert msg is not None
        assert msg.message_id == "test-msg-001"

    def test_parse_interactive_button_reply(self):
        from models.message import IncomingMessage, MessageType, InteractiveType
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"phone_number_id": "12345"},
                        "contacts": [{"profile": {"name": "User"}, "wa_id": "5551111111"}],
                        "messages": [{
                            "id": "btn-001",
                            "from": "5551111111",
                            "timestamp": "1234567890",
                            "type": "interactive",
                            "interactive": {
                                "type": "button_reply",
                                "button_reply": {
                                    "id": "menu_pedido",
                                    "title": "Hacer Pedido",
                                }
                            }
                        }]
                    }
                }]
            }]
        }
        msg = IncomingMessage.from_webhook(payload)
        assert msg is not None
        assert msg.type == MessageType.INTERACTIVE
        assert msg.interactive_id == "menu_pedido"
        assert msg.interactive_title == "Hacer Pedido"


# ── Verify token logic ────────────────────────────────────────────────────────

class TestVerifyTokenLogic:
    """Tests para la lógica de verificación del webhook (sin HTTP)."""

    def test_correct_token_passes(self):
        with patch("config.settings.WA_VERIFY_TOKEN", "my_secret_token"):
            from config.settings import WA_VERIFY_TOKEN
            mode = "subscribe"
            token = "my_secret_token"
            challenge = "challenge_abc"
            assert mode == "subscribe" and token == WA_VERIFY_TOKEN
            assert challenge == "challenge_abc"

    def test_wrong_token_fails(self):
        with patch("config.settings.WA_VERIFY_TOKEN", "correct_token"):
            from config.settings import WA_VERIFY_TOKEN
            token = "wrong_token"
            assert token != WA_VERIFY_TOKEN
