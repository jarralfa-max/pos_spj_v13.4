# tests/test_wa_client.py — SPJ POS v13.5
"""Tests para WhatsAppClient (REST client para el microservicio WA)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from core.integrations.whatsapp_client import WhatsAppClient


class TestWhatsAppClient:
    def test_client_instantiates(self):
        client = WhatsAppClient(base_url="http://localhost:8000")
        assert client.base_url == "http://localhost:8000"

    def test_health_check_returns_false_when_down(self):
        client = WhatsAppClient(base_url="http://localhost:9999", timeout=1)
        assert client.health_check() is False

    def test_notificar_pedido_listo_returns_false_when_down(self):
        client = WhatsAppClient(base_url="http://localhost:9999", timeout=1)
        result = client.notificar_pedido_listo("5551234567", "WA-001")
        assert result is False

    def test_base_url_strips_trailing_slash(self):
        client = WhatsAppClient(base_url="http://localhost:8000/")
        assert not client.base_url.endswith("/")

    def test_enviar_mensaje_returns_false_when_down(self):
        client = WhatsAppClient(base_url="http://localhost:9999", timeout=1)
        assert client.enviar_mensaje("5551234567", "Hola") is False


class TestWhatsAppClientServiceAuthSigning:
    """WA-1: el canal interno ERP↔microservicio ya no usa `X-Internal-Key`
    plano (whatsapp_security_audit.md S1/S2/S3) — cada request se firma con
    HMAC + identidad de servicio (X-Service-Id/X-Timestamp/X-Nonce/
    X-Signature/X-Correlation-Id)."""

    def test_signed_headers_present_and_no_internal_key_header(self):
        client = WhatsAppClient(base_url="http://localhost:8000", internal_key="test-secret")
        headers = client._signed_headers(b'{"phone": "555"}')

        assert "X-Internal-Key" not in headers
        assert headers["X-Service-Id"] == "erp-core"
        assert "X-Timestamp" in headers
        assert "X-Nonce" in headers
        assert "X-Signature" in headers
        assert "X-Correlation-Id" in headers

    def test_signed_headers_empty_when_no_internal_key_configured(self):
        client = WhatsAppClient(base_url="http://localhost:8000", internal_key="")
        assert client._signed_headers(b"{}") == {}

    def test_signature_matches_sign_request_helper(self):
        from core.integrations.whatsapp_client import _sign_request

        client = WhatsAppClient(base_url="http://localhost:8000", internal_key="test-secret")
        body = b'{"phone": "555"}'
        headers = client._signed_headers(body)

        expected = _sign_request(
            "erp-core", headers["X-Timestamp"], headers["X-Nonce"], body, "test-secret"
        )
        assert headers["X-Signature"] == expected

    def test_different_calls_use_different_nonces(self):
        client = WhatsAppClient(base_url="http://localhost:8000", internal_key="test-secret")
        h1 = client._signed_headers(b"{}")
        h2 = client._signed_headers(b"{}")
        assert h1["X-Nonce"] != h2["X-Nonce"]
