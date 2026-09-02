"""WA-1 §5: helpers de redacción (`infrastructure.security.redaction`).

Antes de esto, el enmascarado de credenciales solo existía en
`core/services/whatsapp_credential_service.py:_mask_token` — el
microservicio no tenía ningún equivalente (whatsapp_security_audit.md §4/
Hallazgo 3), y `messaging/sender.py` logueaba el teléfono normalizado
completo en su ruta de éxito/error.
"""
from __future__ import annotations

from infrastructure.security.redaction import redact_phone, redact_secret


def test_redact_phone_keeps_last_4_digits():
    assert redact_phone("+5215512345678") == "***5678"


def test_redact_phone_strips_non_digits_before_masking():
    assert redact_phone("+52 155 1234 5678") == "***5678"


def test_redact_phone_too_short_fully_masked():
    assert redact_phone("12") == "***"


def test_redact_phone_empty():
    assert redact_phone("") == "***"


def test_redact_secret_long_value():
    value = "EAAGabcdef1234567890XYZ"
    expected = value[:4] + "*" * (len(value) - 8) + value[-4:]
    assert redact_secret(value) == expected
    assert redact_secret(value) == "EAAG" + "*" * 15 + "0XYZ"


def test_redact_secret_short_value_fully_masked():
    assert redact_secret("short") == "***"


def test_redact_secret_empty():
    assert redact_secret("") == "***"


def test_redact_secret_matches_secret_store_mask():
    """`SecretStore.mask` y `redact_secret` deben coincidir — mismo patrón
    documentado (`core/services/whatsapp_credential_service.py:_mask_token`)."""
    from infrastructure.secrets.secret_store import SecretStore

    value = "sk-test-1234567890abcdef"
    assert redact_secret(value) == SecretStore.mask(value)
