# tests/test_mercadopago_gateway.py — WA-12
from __future__ import annotations

import asyncio

import pytest

from domain.whatsapp.payment_provider_ports import PaymentLinkRef
from infrastructure.providers.mercadopago.gateway import MercadoPagoGateway, MercadoPagoPreferenceError


class _FakeResponse:
    def __init__(self, status_code=201, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        return self._response


def _run(coro):
    return asyncio.run(coro)


class TestMercadoPagoGateway:
    def test_create_preference_returns_checkout_url(self, monkeypatch):
        import infrastructure.providers.mercadopago.gateway as gateway_mod

        monkeypatch.setattr("config.settings.MP_ACCESS_TOKEN", "token-123")
        monkeypatch.setattr(
            gateway_mod.httpx, "AsyncClient",
            lambda timeout=10.0: _FakeAsyncClient(
                _FakeResponse(201, {"init_point": "https://mp.example/checkout/1", "id": "pref-1"})
            ),
        )
        gateway = MercadoPagoGateway()
        result = _run(gateway.create_preference(amount=100.0, external_reference="order-1:5551234567"))
        assert result == PaymentLinkRef(checkout_url="https://mp.example/checkout/1", preference_id="pref-1")

    def test_raises_when_token_missing(self, monkeypatch):
        monkeypatch.setattr("config.settings.MP_ACCESS_TOKEN", "")
        gateway = MercadoPagoGateway()
        with pytest.raises(MercadoPagoPreferenceError):
            _run(gateway.create_preference(amount=100.0, external_reference="order-1"))

    def test_raises_on_non_success_status(self, monkeypatch):
        import infrastructure.providers.mercadopago.gateway as gateway_mod

        monkeypatch.setattr("config.settings.MP_ACCESS_TOKEN", "token-123")
        monkeypatch.setattr(
            gateway_mod.httpx, "AsyncClient",
            lambda timeout=10.0: _FakeAsyncClient(_FakeResponse(400, {}, text="bad request")),
        )
        gateway = MercadoPagoGateway()
        with pytest.raises(MercadoPagoPreferenceError):
            _run(gateway.create_preference(amount=100.0, external_reference="order-1"))

    def test_raises_when_response_has_no_init_point(self, monkeypatch):
        import infrastructure.providers.mercadopago.gateway as gateway_mod

        monkeypatch.setattr("config.settings.MP_ACCESS_TOKEN", "token-123")
        monkeypatch.setattr(
            gateway_mod.httpx, "AsyncClient",
            lambda timeout=10.0: _FakeAsyncClient(_FakeResponse(201, {"id": "pref-1"})),
        )
        gateway = MercadoPagoGateway()
        with pytest.raises(MercadoPagoPreferenceError):
            _run(gateway.create_preference(amount=100.0, external_reference="order-1"))

    def test_expiration_and_amount_are_sent_in_payload(self, monkeypatch):
        import infrastructure.providers.mercadopago.gateway as gateway_mod

        captured = {}

        class _CapturingClient(_FakeAsyncClient):
            async def post(self, url, json=None, headers=None):
                captured["payload"] = json
                captured["headers"] = headers
                return self._response

        monkeypatch.setattr("config.settings.MP_ACCESS_TOKEN", "token-123")
        monkeypatch.setattr(
            gateway_mod.httpx, "AsyncClient",
            lambda timeout=10.0: _CapturingClient(_FakeResponse(201, {"init_point": "https://x", "id": "p1"})),
        )
        gateway = MercadoPagoGateway()
        _run(gateway.create_preference(amount=250.5, external_reference="order-9:555", description="Pedido F-009"))

        assert captured["payload"]["items"][0]["unit_price"] == 250.5
        assert captured["payload"]["external_reference"] == "order-9:555"
        assert captured["payload"]["items"][0]["title"] == "Pedido F-009"
        assert captured["headers"]["Authorization"] == "Bearer token-123"
