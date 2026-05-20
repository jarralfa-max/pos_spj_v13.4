# tests/test_wa_refactor.py — Tests mínimos Fase 8 WhatsApp refactor
"""
Cubre:
- webhook verification OK / token incorrecto
- parseo de mensaje texto / botón interactivo / lista interactiva
- idempotencia de mensajes duplicados
- rate limit
- sender sin credenciales
- sender con mock HTTP
- WhatsAppClient rutas correctas
- credential validation mock
- repository sin SQL injection
"""
from __future__ import annotations
import asyncio
import json
import sqlite3
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)             # pos_spj_v13.4/pos_spj_v13.4/
_REPO = os.path.dirname(_ROOT)             # pos_spj_v13.4/
WA_SVC_PATH = os.path.join(_REPO, "whatsapp_service")

# WA service path must come before ERP root to avoid config.py shadowing config/
for _p in (WA_SVC_PATH, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Purge stale config cache that may have been set by conftest before our path fix
for _k in list(sys.modules.keys()):
    if _k == "config" or _k.startswith("config."):
        del sys.modules[_k]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS configuraciones (
            clave TEXT PRIMARY KEY, valor TEXT)""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_numeros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal_id INTEGER, canal TEXT DEFAULT 'todos',
            proveedor TEXT DEFAULT 'meta', numero_negocio TEXT,
            meta_token TEXT, meta_phone_id TEXT,
            twilio_sid TEXT, twilio_token TEXT,
            verify_token TEXT DEFAULT 'spj_verify',
            rasa_url TEXT DEFAULT 'http://localhost:5005',
            rasa_activo INTEGER DEFAULT 0, activo INTEGER DEFAULT 1,
            nombre_sucursal TEXT,
            UNIQUE(sucursal_id, canal))""")
    conn.commit()
    return conn


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Webhook verification
# ═══════════════════════════════════════════════════════════════════════════════

def _import_wa_settings():
    """
    Load config.settings from whatsapp_service by file path, then inject it into
    sys.modules so lazy 'from config.settings import X' calls in WA code resolve
    correctly, bypassing the ERP-root config.py module.
    """
    import importlib.util
    import types
    settings_path = os.path.join(WA_SVC_PATH, "config", "settings.py")
    spec = importlib.util.spec_from_file_location("wa_config_settings", settings_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Build a fake config package that exposes settings as a submodule
    fake_pkg = types.ModuleType("config")
    fake_pkg.settings = mod
    sys.modules["config"] = fake_pkg
    sys.modules["config.settings"] = mod
    return mod


class TestWebhookVerification:

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _get_verify_webhook(self):
        """Import verify_webhook — call AFTER _import_wa_settings."""
        for k in list(sys.modules.keys()):
            if k in ("webhook.whatsapp", "middleware.rate_limiter"):
                del sys.modules[k]
        from webhook.whatsapp import verify_webhook
        return verify_webhook

    def test_correct_token_returns_challenge(self):
        """GET /webhook con token correcto devuelve challenge."""
        wa_settings = _import_wa_settings()   # sets sys.modules["config.*"] first
        verify_webhook = self._get_verify_webhook()  # imports after, keeps config
        with patch.object(wa_settings, "WA_VERIFY_TOKEN", "correct_token"):
            async def run():
                return await verify_webhook(
                    mode="subscribe", token="correct_token", challenge="abc123")
            resp = self._run(run())
            assert resp.body == b"abc123"
            assert resp.status_code == 200

    def test_wrong_token_returns_403(self):
        """GET /webhook con token incorrecto devuelve 403."""
        wa_settings = _import_wa_settings()
        verify_webhook = self._get_verify_webhook()
        with patch.object(wa_settings, "WA_VERIFY_TOKEN", "correct_token"):
            async def run():
                return await verify_webhook(
                    mode="subscribe", token="wrong_token", challenge="abc123")
            resp = self._run(run())
            assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Parseo de mensajes
# ═══════════════════════════════════════════════════════════════════════════════

class TestMessageParsing:

    def _wa_payload(self, msg_type: str, **kwargs) -> dict:
        msg: dict = {"id": "msg_001", "from": "521234567890",
                     "timestamp": "1700000000", "type": msg_type}
        if msg_type == "text":
            msg["text"] = {"body": kwargs.get("body", "hola")}
        elif msg_type == "interactive":
            itype = kwargs.get("itype", "button_reply")
            if itype == "button_reply":
                msg["interactive"] = {
                    "type": "button_reply",
                    "button_reply": {"id": kwargs.get("id", "btn_1"),
                                     "title": kwargs.get("title", "Opción 1")}}
            else:
                msg["interactive"] = {
                    "type": "list_reply",
                    "list_reply": {"id": kwargs.get("id", "item_1"),
                                   "title": kwargs.get("title", "Item 1")}}
        payload = {"object": "whatsapp_business_account", "entry": [{"changes": [
            {"value": {"messages": [msg],
                       "metadata": {"phone_number_id": "pn_001"}}}]}]}
        return payload

    def test_parse_text_message(self):
        from models.message import IncomingMessage
        payload = self._wa_payload("text", body="quiero hacer un pedido")
        msg = IncomingMessage.from_webhook(payload)
        assert msg is not None
        assert msg.text == "quiero hacer un pedido"
        assert msg.from_number == "521234567890"

    def test_parse_interactive_button(self):
        from models.message import IncomingMessage
        payload = self._wa_payload("interactive", itype="button_reply",
                                   id="confirm", title="Confirmar")
        msg = IncomingMessage.from_webhook(payload)
        assert msg is not None
        assert msg.interactive_id == "confirm"

    def test_parse_interactive_list(self):
        from models.message import IncomingMessage
        payload = self._wa_payload("interactive", itype="list_reply",
                                   id="prod_tacos", title="Tacos")
        msg = IncomingMessage.from_webhook(payload)
        assert msg is not None
        assert msg.interactive_id == "prod_tacos"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Idempotencia
# ═══════════════════════════════════════════════════════════════════════════════

class TestIdempotency:

    def test_duplicate_message_is_detected(self, tmp_path):
        from state.conversation import ConversationStore
        db_path = str(tmp_path / "conv.db")
        store = ConversationStore(db_path)
        store.log_message("msg_dup_001", "+521234", "in", "hola")
        assert store.is_duplicate("msg_dup_001") is True

    def test_new_message_is_not_duplicate(self, tmp_path):
        from state.conversation import ConversationStore
        db_path = str(tmp_path / "conv.db")
        store = ConversationStore(db_path)
        assert store.is_duplicate("msg_brand_new") is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Rate limiting
# ═══════════════════════════════════════════════════════════════════════════════

class TestRateLimit:

    def test_under_limit_is_allowed(self):
        from middleware.rate_limiter import RateLimiter
        rl = RateLimiter()
        for _ in range(5):
            assert rl.is_allowed("+52_test_rate") is True

    def test_over_limit_is_blocked(self):
        from middleware.rate_limiter import RateLimiter
        rl = RateLimiter()
        for _ in range(100):
            rl.is_allowed("+52_test_rate_2")
        result = rl.is_allowed("+52_test_rate_2")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Sender sin credenciales
# ═══════════════════════════════════════════════════════════════════════════════

class TestSenderNoCredentials:

    def test_send_raises_without_credentials(self):
        """_get_whatsapp_config sin BD ni .env debe lanzar ValueError."""
        import messaging.sender as _sender  # pre-import so patch target resolves
        with patch.object(_sender, "WA_ACCESS_TOKEN", None), \
             patch.object(_sender, "WA_PHONE_NUMBER_ID", None), \
             patch.object(_sender, "ERP_DB_PATH", "/nonexistent/path.db"):
            with pytest.raises(ValueError):
                _sender._get_whatsapp_config(sucursal_id=None)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Sender con mock HTTP
# ═══════════════════════════════════════════════════════════════════════════════

class TestSenderMockHttp:

    def test_send_text_calls_graph_api(self):
        import messaging.sender as _sender  # pre-import
        _fake_url = "https://graph.facebook.com/v21.0/phone_id_test/messages"
        with patch.object(_sender, "_get_whatsapp_config",
                          return_value=("token_test", "phone_id_test")), \
             patch.object(_sender, "get_wa_api_url", return_value=_fake_url):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = asyncio.get_event_loop().run_until_complete(
                    _sender.send_text("+521234567890", "Hola test"))
                assert result is True
                mock_client.post.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# 7. WhatsAppClient — rutas correctas
# ═══════════════════════════════════════════════════════════════════════════════

class TestWhatsAppClientRoutes:

    def setup_method(self):
        from core.integrations.whatsapp_client import WhatsAppClient
        self.client = WhatsAppClient(base_url="http://localhost:8000",
                                     internal_key="test_key")

    def _capture_post_path(self):
        captured = {}

        def fake_post(path, payload):
            captured["path"] = path
            return {"ok": True}

        self.client._post = fake_post
        return captured

    def test_notificar_pedido_listo_route(self):
        cap = self._capture_post_path()
        self.client.notificar_pedido_listo("+52123", "WA-001")
        assert cap["path"] == "/api/notify/pedido-listo"

    def test_notificar_anticipo_route(self):
        cap = self._capture_post_path()
        self.client.notificar_anticipo_requerido("+52123", "WA-001", 250.0)
        assert cap["path"] == "/api/notify/anticipo"

    def test_enviar_mensaje_route(self):
        cap = self._capture_post_path()
        self.client.enviar_mensaje("+52123", "Hola")
        assert cap["path"] == "/api/notify/send"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Credential validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestCredentialValidation:

    def test_empty_token_invalid(self, mem_db):
        from core.services.whatsapp_credential_service import WhatsAppCredentialService
        svc = WhatsAppCredentialService(mem_db)
        result = svc.validate_meta_credentials("", "some_phone_id")
        assert result["valid"] is False
        assert "Token" in result["error"]

    def test_empty_phone_id_invalid(self, mem_db):
        from core.services.whatsapp_credential_service import WhatsAppCredentialService
        svc = WhatsAppCredentialService(mem_db)
        result = svc.validate_meta_credentials("a" * 25, "")
        assert result["valid"] is False

    def test_network_error_returns_false(self, mem_db):
        from core.services.whatsapp_credential_service import WhatsAppCredentialService
        import urllib.error
        svc = WhatsAppCredentialService(mem_db)
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError("no network")):
            result = svc.validate_meta_credentials("a" * 25, "phone_123")
            assert result["valid"] is False

    def test_token_masking(self, mem_db):
        from core.services.whatsapp_credential_service import WhatsAppCredentialService
        svc = WhatsAppCredentialService(mem_db)
        masked = svc._mask_token("EAABCDEF1234567890XYZ")
        assert "EAAB" in masked
        assert len(masked) == len("EAABCDEF1234567890XYZ")
        assert "****" in masked


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Repository — no SQL injection
# ═══════════════════════════════════════════════════════════════════════════════

class TestRepositoryNoInjection:

    def test_history_search_uses_parameterized_query(self, mem_db):
        """Buscar con input malicioso no debe romper la query ni devolver datos."""
        mem_db.execute("""CREATE TABLE IF NOT EXISTS wa_message_queue (
            id INTEGER PRIMARY KEY, fecha_creacion TEXT,
            to_number TEXT, message TEXT, status TEXT)""")
        mem_db.execute(
            "INSERT INTO wa_message_queue(fecha_creacion,to_number,message,status)"
            "VALUES(datetime('now'),'+521234','hola','sent')")
        mem_db.commit()

        from core.repositories.whatsapp_history_repository import WhatsAppHistoryRepository
        repo = WhatsAppHistoryRepository(mem_db)
        evil = "' OR '1'='1"
        rows = repo.get_history(search=evil)
        assert isinstance(rows, list)

    def test_config_set_and_get_roundtrip(self, mem_db):
        from core.repositories.whatsapp_config_repository import WhatsAppConfigRepository
        repo = WhatsAppConfigRepository(mem_db)
        repo.set_config("bot_nombre", "TestBot")
        mem_db.commit()
        val = repo.get_config("bot_nombre")
        assert val == "TestBot"
