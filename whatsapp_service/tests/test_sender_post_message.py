# tests/test_sender_post_message.py — WA-5
"""`messaging.sender._post_message` — extraído en WA-5 de lo que antes era
código HTTP duplicado inline en `send_message`/`send_template`. Único
punto real de envío hacia la Graph API; `MetaCloudApiWhatsAppGateway`
(WA-5) también pasa por aquí."""
from __future__ import annotations

import asyncio

import httpx
import pytest

import messaging.sender as sender_mod


class _FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise_exc = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        if self._raise_exc:
            raise self._raise_exc
        return self._response


def _patch_client(monkeypatch, *, response=None, raise_exc=None):
    monkeypatch.setattr(
        sender_mod.httpx, "AsyncClient",
        lambda timeout=10.0: _FakeAsyncClient(response=response, raise_exc=raise_exc),
    )


class TestPostMessage:
    def test_success_extracts_provider_message_id(self, monkeypatch):
        _patch_client(monkeypatch, response=_FakeResponse(
            200, json_data={"messages": [{"id": "wamid.abc"}]}
        ))
        result = asyncio.run(sender_mod._post_message("http://x", {}, {}))
        assert result == {
            "ok": True, "status_code": 200, "provider_message_id": "wamid.abc",
            "error": None, "raw": {"messages": [{"id": "wamid.abc"}]},
        }

    def test_success_without_messages_array_has_none_id(self, monkeypatch):
        _patch_client(monkeypatch, response=_FakeResponse(200, json_data={"contacts": []}))
        result = asyncio.run(sender_mod._post_message("http://x", {}, {}))
        assert result["ok"] is True
        assert result["provider_message_id"] is None

    def test_non_200_status_is_error(self, monkeypatch):
        _patch_client(monkeypatch, response=_FakeResponse(400, text="bad request"))
        result = asyncio.run(sender_mod._post_message("http://x", {}, {}))
        assert result["ok"] is False
        assert result["status_code"] == 400
        assert result["error"] == "bad request"

    def test_timeout_is_normalized_not_raised(self, monkeypatch):
        _patch_client(monkeypatch, raise_exc=httpx.TimeoutException("timed out"))
        result = asyncio.run(sender_mod._post_message("http://x", {}, {}))
        assert result["ok"] is False
        assert result["error"] == "timeout"

    def test_unexpected_exception_is_normalized_not_raised(self, monkeypatch):
        _patch_client(monkeypatch, raise_exc=RuntimeError("boom"))
        result = asyncio.run(sender_mod._post_message("http://x", {}, {}))
        assert result["ok"] is False
        assert "boom" in result["error"]

    def test_malformed_json_on_200_still_reports_ok(self, monkeypatch):
        response = _FakeResponse(200, json_data=None)  # .json() raises
        _patch_client(monkeypatch, response=response)
        result = asyncio.run(sender_mod._post_message("http://x", {}, {}))
        assert result["ok"] is True
        assert result["provider_message_id"] is None
        assert result["raw"] is None
