# tests/test_meta_cloud_api_gateway.py — WA-5
"""`MetaCloudApiWhatsAppGateway` — implementación de
`domain.whatsapp.provider_ports.WhatsAppProviderGateway`. Ningún test aquí
toca la red real: `send_*`/`mark_read` mockean
`messaging.sender._post_message` (el único punto real de envío, compartido
con `send_message`/`send_template`); `download_media`/`health_check`
mockean `httpx` con clientes falsos."""
from __future__ import annotations

import asyncio

import pytest

import infrastructure.providers.meta_cloud_api.gateway as gateway_mod
from infrastructure.providers.meta_cloud_api.gateway import MetaCloudApiWhatsAppGateway


def _gateway() -> MetaCloudApiWhatsAppGateway:
    return MetaCloudApiWhatsAppGateway()


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    """Config resuelta por defecto en todos los tests de esta suite —
    cada test que necesite un escenario distinto la sobreescribe."""
    import messaging.sender as sender_mod

    monkeypatch.setattr(sender_mod, "_get_whatsapp_config", lambda sucursal_id=None: ("token", "phone-id"))
    monkeypatch.setattr(sender_mod, "_is_whatsapp_opted_out", lambda phone: False)


def _mock_post_message(monkeypatch, result: dict):
    import messaging.sender as sender_mod

    async def _fake(url, payload, headers, timeout=10.0):
        _fake.calls.append((url, payload, headers))
        return result

    _fake.calls = []
    monkeypatch.setattr(sender_mod, "_post_message", _fake)
    return _fake


class TestSendText:
    def test_success_returns_provider_message_id(self, monkeypatch):
        fake = _mock_post_message(
            monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": "wamid.1", "error": None, "raw": {}}
        )
        result = asyncio.run(_gateway().send_text(to="5512345678", body="hola"))
        assert result["ok"] is True
        assert result["provider_message_id"] == "wamid.1"
        assert fake.calls[0][1]["type"] == "text"
        assert fake.calls[0][1]["text"]["body"] == "hola"
        assert fake.calls[0][1]["to"] == "+525512345678"

    def test_failure_propagates_error(self, monkeypatch):
        _mock_post_message(
            monkeypatch, {"ok": False, "status_code": 500, "provider_message_id": None, "error": "boom", "raw": None}
        )
        result = asyncio.run(_gateway().send_text(to="5512345678", body="hola"))
        assert result["ok"] is False
        assert result["error"] == "boom"

    def test_opted_out_never_calls_post_message(self, monkeypatch):
        import messaging.sender as sender_mod

        monkeypatch.setattr(sender_mod, "_is_whatsapp_opted_out", lambda phone: True)
        fake = _mock_post_message(monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": "x", "error": None, "raw": {}})
        result = asyncio.run(_gateway().send_text(to="5512345678", body="hola"))
        assert result["ok"] is False
        assert result["error"] == "opted_out"
        assert fake.calls == []

    def test_invalid_phone_never_calls_post_message(self, monkeypatch):
        fake = _mock_post_message(monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": "x", "error": None, "raw": {}})
        result = asyncio.run(_gateway().send_text(to="", body="hola"))
        assert result["ok"] is False
        assert fake.calls == []

    def test_missing_config_never_calls_post_message(self, monkeypatch):
        import messaging.sender as sender_mod

        def _raise(sucursal_id=None):
            raise ValueError("no config")

        monkeypatch.setattr(sender_mod, "_get_whatsapp_config", _raise)
        fake = _mock_post_message(monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": "x", "error": None, "raw": {}})
        result = asyncio.run(_gateway().send_text(to="5512345678", body="hola"))
        assert result["ok"] is False
        assert fake.calls == []


class TestSendTemplate:
    def test_builds_positional_body_parameters_in_order(self, monkeypatch):
        fake = _mock_post_message(monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": "wamid.2", "error": None, "raw": {}})
        result = asyncio.run(
            _gateway().send_template(
                to="5512345678", template_name="pedido_confirmado", language="es_MX",
                parameters={"folio": "F1", "total": "$100.00"},
            )
        )
        assert result["ok"] is True
        payload = fake.calls[0][1]
        assert payload["template"]["name"] == "pedido_confirmado"
        params = payload["template"]["components"][0]["parameters"]
        assert [p["text"] for p in params] == ["F1", "$100.00"]

    def test_no_parameters_omits_components(self, monkeypatch):
        fake = _mock_post_message(monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": "x", "error": None, "raw": {}})
        asyncio.run(_gateway().send_template(to="5512345678", template_name="t", language="es_MX", parameters={}))
        assert "components" not in fake.calls[0][1]["template"]


class TestSendInteractive:
    def test_wraps_interactive_payload_as_is(self, monkeypatch):
        fake = _mock_post_message(monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": "x", "error": None, "raw": {}})
        interactive_payload = {"type": "button", "body": {"text": "hola"}, "action": {"buttons": []}}
        asyncio.run(_gateway().send_interactive(to="5512345678", payload=interactive_payload))
        sent = fake.calls[0][1]
        assert sent["type"] == "interactive"
        assert sent["interactive"] == interactive_payload


class TestSendMedia:
    def test_rejects_unsupported_media_type(self, monkeypatch):
        fake = _mock_post_message(monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": "x", "error": None, "raw": {}})
        result = asyncio.run(_gateway().send_media(to="5512345678", media_type="gif", media_reference="123"))
        assert result["ok"] is False
        assert "no soportado" in result["error"]
        assert fake.calls == []

    def test_link_reference_uses_link_key(self, monkeypatch):
        fake = _mock_post_message(monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": "x", "error": None, "raw": {}})
        asyncio.run(_gateway().send_media(to="5512345678", media_type="image", media_reference="https://example.com/a.jpg"))
        assert fake.calls[0][1]["image"] == {"link": "https://example.com/a.jpg"}

    def test_id_reference_uses_id_key(self, monkeypatch):
        fake = _mock_post_message(monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": "x", "error": None, "raw": {}})
        asyncio.run(_gateway().send_media(to="5512345678", media_type="document", media_reference="1234567890"))
        assert fake.calls[0][1]["document"] == {"id": "1234567890"}


class TestMarkRead:
    def test_sends_status_read_payload(self, monkeypatch):
        fake = _mock_post_message(monkeypatch, {"ok": True, "status_code": 200, "provider_message_id": None, "error": None, "raw": {}})
        asyncio.run(_gateway().mark_read(provider_message_id="wamid.99"))
        assert fake.calls[0][1] == {
            "messaging_product": "whatsapp", "status": "read", "message_id": "wamid.99",
        }

    def test_missing_config_does_not_raise(self, monkeypatch):
        import messaging.sender as sender_mod

        def _raise(sucursal_id=None):
            raise ValueError("no config")

        monkeypatch.setattr(sender_mod, "_get_whatsapp_config", _raise)
        asyncio.run(_gateway().mark_read(provider_message_id="wamid.99"))  # no debe lanzar


class TestGetMessageStatus:
    def test_always_returns_none(self):
        """Meta Cloud API no expone polling de estado — ver docstring del
        método. El estado real llega por webhook (WA-6)."""
        result = asyncio.run(_gateway().get_message_status(provider_message_id="wamid.1"))
        assert result is None


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b"", text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.content = content
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        return self._responses.pop(0)


class TestDownloadMedia:
    def test_two_step_download(self, monkeypatch):
        responses = [
            _FakeResponse(json_data={"url": "https://signed.example.com/file"}),
            _FakeResponse(content=b"binary-bytes"),
        ]
        monkeypatch.setattr(gateway_mod.httpx, "AsyncClient", lambda timeout=15.0: _FakeAsyncClient(responses))
        content = asyncio.run(_gateway().download_media(media_id="media-1"))
        assert content == b"binary-bytes"

    def test_metadata_fetch_failure_propagates(self, monkeypatch):
        responses = [_FakeResponse(status_code=404)]
        monkeypatch.setattr(gateway_mod.httpx, "AsyncClient", lambda timeout=15.0: _FakeAsyncClient(responses))
        with pytest.raises(RuntimeError):
            asyncio.run(_gateway().download_media(media_id="missing"))


class _FakeSyncClient:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers=None):
        return self._response


class TestHealthCheck:
    def test_true_when_ping_returns_200(self, monkeypatch):
        monkeypatch.setattr(
            gateway_mod.httpx, "Client", lambda timeout=5.0: _FakeSyncClient(_FakeResponse(status_code=200))
        )
        assert _gateway().health_check() is True

    def test_false_when_ping_returns_error_status(self, monkeypatch):
        monkeypatch.setattr(
            gateway_mod.httpx, "Client", lambda timeout=5.0: _FakeSyncClient(_FakeResponse(status_code=401))
        )
        assert _gateway().health_check() is False

    def test_false_when_config_missing(self, monkeypatch):
        import messaging.sender as sender_mod

        def _raise(sucursal_id=None):
            raise ValueError("no config")

        monkeypatch.setattr(sender_mod, "_get_whatsapp_config", _raise)
        assert _gateway().health_check() is False

    def test_false_when_network_raises(self, monkeypatch):
        class _Boom:
            def __enter__(self):
                raise ConnectionError("no network")

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(gateway_mod.httpx, "Client", lambda timeout=5.0: _Boom())
        assert _gateway().health_check() is False
