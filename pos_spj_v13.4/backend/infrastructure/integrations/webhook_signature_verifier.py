"""WebhookSignatureVerifier — SET-19 "Webhooks". Implements
`backend.domain.integrations.webhook_verification_ports.WebhookSignatureVerifierPort`.

Deliberately **reimplements**, rather than imports,
`whatsapp_service/middleware/hmac_validator.py`'s two functions
(`verify_signature`, `verify_mp_signature`) — WhatsApp is a separate,
independently-deployed FastAPI microservice (CLAUDE.md §14: "Arquitecto
como servicio independiente"), and this backend must not import across
that service boundary. Both schemes are stateless, well-specified HMAC
verification with no hardware/vendor dependency, so — the same "safe to
build for real" judgment SET-12 made for print routing — this is a real
adapter, faithfully mirroring the reference implementation's logic byte
for byte, not a Protocol stub.
"""

from __future__ import annotations

import hashlib
import hmac

from backend.domain.integrations.enums import WebhookSignatureScheme

_HEADER_SIGNATURE = "X-Hub-Signature-256"
_HEADER_MP_SIGNATURE = "X-Signature"
_HEADER_MP_REQUEST_ID = "X-Request-Id"


class WebhookSignatureVerifier:
    def verify(self, *, scheme: WebhookSignatureScheme, headers: dict, body: bytes, secret: str) -> bool:
        if scheme is WebhookSignatureScheme.NONE:
            return True
        if scheme is WebhookSignatureScheme.HMAC_SHA256_HEADER:
            return self._verify_hmac_sha256_header(headers, body, secret)
        if scheme is WebhookSignatureScheme.MERCADOPAGO_TS_V1:
            return self._verify_mercadopago_ts_v1(headers, secret)
        return False

    @staticmethod
    def _verify_hmac_sha256_header(headers: dict, body: bytes, secret: str) -> bool:
        sig_header = headers.get(_HEADER_SIGNATURE, "")
        if not sig_header.startswith("sha256=") or not secret:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig_header[len("sha256="):])

    @staticmethod
    def _verify_mercadopago_ts_v1(headers: dict, secret: str) -> bool:
        x_signature = headers.get(_HEADER_MP_SIGNATURE, "")
        x_request_id = headers.get(_HEADER_MP_REQUEST_ID, "")
        data_id = headers.get("data_id", "")
        if not x_signature or not secret:
            return False
        parts = dict(item.split("=", 1) for item in x_signature.split(",") if "=" in item)
        ts = parts.get("ts", "").strip()
        v1 = parts.get("v1", "").strip()
        if not ts or not v1:
            return False
        manifest = f"id:{(data_id or '').lower()};request-id:{x_request_id or ''};ts:{ts};"
        expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, v1)
