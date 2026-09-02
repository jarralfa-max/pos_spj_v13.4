# middleware/hmac_validator.py
"""HMAC-SHA256 validation for Meta and MercadoPago webhook signatures."""
from __future__ import annotations
import hashlib
import hmac
import time


def verify_signature(body: bytes, sig_header: str, app_secret: str) -> bool:
    """Return True if X-Hub-Signature-256 matches body signed with app_secret."""
    if not sig_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header[7:])


def verify_mp_signature(
    x_signature: str,
    x_request_id: str,
    data_id: str,
    secret: str,
    max_age_seconds: int = 300,
) -> bool:
    """Return True if MercadoPago's X-Signature header matches `secret`.

    Per MercadoPago's documented validation (Payments event webhook,
    `action` in {"payment.created", "payment.updated"}):

    - `X-Signature` carries `ts=<millis>,v1=<hex hmac>` (comma-separated).
    - `data_id` is the `data.id` **query-string** parameter of the
      notification URL (lower-cased), not the JSON body's `data.id`.
    - manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
    - v1 must equal HMAC-SHA256(manifest, secret) hex digest.

    WA-1 replay protection (whatsapp_security_audit.md, Hallazgo adicional
    §2 / S9): a validly-signed-but-old `ts` (a captured-and-replayed request)
    is now rejected if it falls outside `max_age_seconds` of the server
    clock. `ts` is milliseconds per MercadoPago's own manifest format above.
    Only applied here — the Meta webhook's `X-Hub-Signature-256` scheme has
    no timestamp in the signed payload, so there's no sound way to bound
    replay at the signature layer for it (see webhook/whatsapp.py comment).
    """
    if not x_signature or not secret:
        return False
    parts = dict(
        item.split("=", 1) for item in x_signature.split(",") if "=" in item
    )
    ts = parts.get("ts", "").strip()
    v1 = parts.get("v1", "").strip()
    if not ts or not v1:
        return False
    manifest = f"id:{(data_id or '').lower()};request-id:{x_request_id or ''};ts:{ts};"
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1):
        return False

    try:
        ts_ms = int(ts)
    except ValueError:
        return False
    now_ms = int(time.time() * 1000)
    if abs(now_ms - ts_ms) > max_age_seconds * 1000:
        return False

    return True
