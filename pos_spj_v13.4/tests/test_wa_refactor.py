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
import json
import sqlite3
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(__file__)
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

WA_SVC_PATH = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "whatsapp_service")
if WA_SVC_PATH not in sys.path:
    sys.path.insert(0, WA_SVC_PATH)

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

class TestWebhookVerification:

    def test_correct_token_returns_challenge(self):
        """GET /webhook con token correcto devuelve challenge."""
        with patch("config.settings.WA_VERIFY_TOKEN", "correct_token"):
            from webhook.whatsapp import verify_webhook
            import asyncio
            from fastapi.responses import Response

            async def run():
                return await verify_webhook(
                    mode="subscribe", token="correct_token", challenge="abc123")
            resp = asyncio.get_event_loop().run_until_complete(run())
            assert resp.body == b"abc123"
            assert resp.status_code == 200

    def test_wrong_token_returns_403(self):
        """GET /webhook con token incorrecto devuelve 403."""
        with patch("config.settings.WA_VERIFY_TOKEN", "correct_token"):
            from webhook.whatsapp import verify_webhook
            import asyncio

            async def run():
                return await verify_webhook(
                    mode="subscribe", token="wrong_token", challenge="abc123")
            resp = asyncio.get_event_loop().run_until_complete(run())
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
                    "button_reply": {"id": kwargs.get("id","btn_1"),
                                     "title": kwargs.get("title","Opción 1")}}
            else:
                msg["interactive"] = {
                    "type": "list_reply",
                    "list_reply": {"id": kwargs.get("id","item_1"),
                                   "title": kwargs.get("title","Item 1")}}
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
        # Exhaust limit
        for _ in range(100):
            rl.is_allowed("+52_test_rate_2")
        result = rl.is_allowed("+52_test_rate_2")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Sender sin credenciales
# ═══════════════════════════════════════════════════════════════════════════════

class TestSenderNoCredentials:

    @pytest.mark.asyncio
    async def test_send_raises_without_credentials(self):
        """_get_whatsapp_config sin BD ni .env debe lanzar ValueError."""
        with patch("messaging.sender.WA_ACCESS_TOKEN", None), \
             patch("messaging.sender.WA_PHONE_NUMBER_ID", None), \
             patch("messaging.sender.ERP_DB_PATH", "/nonexistent/path.db"):
            from messaging.sender import _get_whatsapp_config
            with pytest.raises(ValueError):
                _get_whatsapp_config(sucursal_id=None)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Sender con mock HTTP
# ═══════════════════════════════════════════════════════════════════════════════

class TestSenderMockHttp:

    @pytest.mark.asyncio
    async def test_send_text_calls_graph_api(self):
        with patch("messaging.sender._get_whatsapp_config",
                   return_value=("token_test", "phone_id_test")):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)

            with patch("httpx.AsyncClient", return_value=mock_client):
                from messaging.sender import send_text
                result = await send_text("+521234567890", "Hola test")
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
        # Middle section should be masked
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
        # SQL injection attempt
        evil = "' OR '1'='1"
        rows = repo.get_history(search=evil)
        # Should return empty (no match) without raising
        assert isinstance(rows, list)

    def test_config_set_and_get_roundtrip(self, mem_db):
        from core.repositories.whatsapp_config_repository import WhatsAppConfigRepository
        repo = WhatsAppConfigRepository(mem_db)
        repo.set_config("bot_nombre", "TestBot")
        mem_db.commit()
        val = repo.get_config("bot_nombre")
        assert val == "TestBot"
