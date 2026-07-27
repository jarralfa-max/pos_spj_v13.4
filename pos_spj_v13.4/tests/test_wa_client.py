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
