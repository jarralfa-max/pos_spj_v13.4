# middleware/hmac_validator.py
"""HMAC-SHA256 validation for Meta webhook signatures."""
from __future__ import annotations
import hashlib
import hmac


def verify_signature(body: bytes, sig_header: str, app_secret: str) -> bool:
    """Return True if X-Hub-Signature-256 matches body signed with app_secret."""
    if not sig_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header[7:])
