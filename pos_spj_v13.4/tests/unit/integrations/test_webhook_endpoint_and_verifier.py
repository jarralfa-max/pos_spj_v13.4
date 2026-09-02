"""SET-19 — "Webhooks": WebhookEndpoint entity + WebhookSignatureVerifier
(a real adapter, not a Protocol stub — see its own module docstring for
why). Verified against the same test vectors
`whatsapp_service/tests/test_mercadopago_webhook_signature.py`-style
schemes use, computed independently here. Pure domain — no DB.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from backend.domain.integrations.entities.webhook_endpoint import WebhookEndpoint
from backend.domain.integrations.enums import WebhookSignatureScheme
from backend.domain.integrations.exceptions import IntegrationsInvalidValueError
from backend.infrastructure.integrations.webhook_signature_verifier import WebhookSignatureVerifier
from backend.shared.ids import is_uuidv7, new_uuid


def _endpoint(**overrides) -> WebhookEndpoint:
    kwargs = dict(instance_id=new_uuid(), code="whatsapp_inbound", path="/webhooks/whatsapp")
    kwargs.update(overrides)
    return WebhookEndpoint.create(**kwargs)


class TestWebhookEndpointCreate:
    def test_mints_uuidv7_and_defaults_to_no_signature(self):
        endpoint = _endpoint()
        assert is_uuidv7(endpoint.id)
        assert endpoint.signature_scheme is WebhookSignatureScheme.NONE
        assert endpoint.active is True
        assert endpoint.last_received_at is None

    def test_requires_code(self):
        with pytest.raises(IntegrationsInvalidValueError):
            _endpoint(code="   ")

    def test_requires_path_to_start_with_slash(self):
        with pytest.raises(IntegrationsInvalidValueError):
            _endpoint(path="webhooks/whatsapp")

    def test_scheme_requires_signing_secret_reference(self):
        with pytest.raises(IntegrationsInvalidValueError):
            _endpoint(signature_scheme=WebhookSignatureScheme.HMAC_SHA256_HEADER)

    def test_scheme_with_reference_is_accepted(self):
        endpoint = _endpoint(
            signature_scheme=WebhookSignatureScheme.HMAC_SHA256_HEADER,
            signing_secret_reference="whatsapp/app_secret",
        )
        assert endpoint.signature_scheme is WebhookSignatureScheme.HMAC_SHA256_HEADER

    def test_activate_deactivate(self):
        endpoint = _endpoint()
        endpoint.deactivate()
        assert endpoint.active is False
        endpoint.activate()
        assert endpoint.active is True

    def test_mark_received_sets_timestamp(self):
        endpoint = _endpoint()
        endpoint.mark_received()
        assert endpoint.last_received_at is not None


class TestWebhookSignatureVerifierNoneScheme:
    def test_none_scheme_always_verifies(self):
        verifier = WebhookSignatureVerifier()
        assert verifier.verify(scheme=WebhookSignatureScheme.NONE, headers={}, body=b"", secret="") is True


class TestWebhookSignatureVerifierHmacHeader:
    def test_valid_signature_verifies(self):
        secret = "topsecret"
        body = b'{"hello":"world"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        verifier = WebhookSignatureVerifier()
        assert verifier.verify(
            scheme=WebhookSignatureScheme.HMAC_SHA256_HEADER, headers={"X-Hub-Signature-256": sig},
            body=body, secret=secret,
        ) is True

    def test_wrong_secret_fails(self):
        body = b'{"hello":"world"}'
        sig = "sha256=" + hmac.new(b"other-secret", body, hashlib.sha256).hexdigest()
        verifier = WebhookSignatureVerifier()
        assert verifier.verify(
            scheme=WebhookSignatureScheme.HMAC_SHA256_HEADER, headers={"X-Hub-Signature-256": sig},
            body=body, secret="topsecret",
        ) is False

    def test_missing_header_fails(self):
        verifier = WebhookSignatureVerifier()
        assert verifier.verify(
            scheme=WebhookSignatureScheme.HMAC_SHA256_HEADER, headers={}, body=b"x", secret="topsecret",
        ) is False

    def test_malformed_header_fails_without_raising(self):
        verifier = WebhookSignatureVerifier()
        assert verifier.verify(
            scheme=WebhookSignatureScheme.HMAC_SHA256_HEADER, headers={"X-Hub-Signature-256": "not-sha256"},
            body=b"x", secret="topsecret",
        ) is False

    def test_tampered_body_fails(self):
        secret = "topsecret"
        original_body = b'{"amount":10}'
        sig = "sha256=" + hmac.new(secret.encode(), original_body, hashlib.sha256).hexdigest()
        verifier = WebhookSignatureVerifier()
        tampered_body = b'{"amount":10000}'
        assert verifier.verify(
            scheme=WebhookSignatureScheme.HMAC_SHA256_HEADER, headers={"X-Hub-Signature-256": sig},
            body=tampered_body, secret=secret,
        ) is False


class TestWebhookSignatureVerifierMercadoPago:
    def _valid_headers(self, *, secret: str, data_id: str = "123", request_id: str = "req-1", ts: str = "1700000000000") -> dict:
        manifest = f"id:{data_id.lower()};request-id:{request_id};ts:{ts};"
        v1 = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
        return {"X-Signature": f"ts={ts},v1={v1}", "X-Request-Id": request_id, "data_id": data_id}

    def test_valid_signature_verifies(self):
        secret = "mp-secret"
        verifier = WebhookSignatureVerifier()
        assert verifier.verify(
            scheme=WebhookSignatureScheme.MERCADOPAGO_TS_V1, headers=self._valid_headers(secret=secret),
            body=b"", secret=secret,
        ) is True

    def test_wrong_secret_fails(self):
        verifier = WebhookSignatureVerifier()
        headers = self._valid_headers(secret="mp-secret")
        assert verifier.verify(
            scheme=WebhookSignatureScheme.MERCADOPAGO_TS_V1, headers=headers, body=b"", secret="wrong",
        ) is False

    def test_tampered_data_id_fails(self):
        secret = "mp-secret"
        headers = self._valid_headers(secret=secret, data_id="123")
        headers["data_id"] = "999"  # tampered after signing
        verifier = WebhookSignatureVerifier()
        assert verifier.verify(
            scheme=WebhookSignatureScheme.MERCADOPAGO_TS_V1, headers=headers, body=b"", secret=secret,
        ) is False

    def test_missing_signature_header_fails(self):
        verifier = WebhookSignatureVerifier()
        assert verifier.verify(
            scheme=WebhookSignatureScheme.MERCADOPAGO_TS_V1, headers={}, body=b"", secret="mp-secret",
        ) is False

    def test_data_id_is_case_insensitive(self):
        # Signed with the lower-cased data_id (MercadoPago's own documented
        # scheme signs the lower-cased value); the header we receive can
        # still arrive upper-cased and must verify identically.
        secret = "mp-secret"
        headers = self._valid_headers(secret=secret, data_id="abc")
        headers["data_id"] = "ABC"
        verifier = WebhookSignatureVerifier()
        assert verifier.verify(
            scheme=WebhookSignatureScheme.MERCADOPAGO_TS_V1, headers=headers, body=b"", secret=secret,
        ) is True
