# infrastructure/security/redaction.py — redacción de datos sensibles (WA-1)
"""
Helpers de enmascarado para logs. Ver whatsapp_security_audit.md §4: antes de
esto el microservicio no tenía ningún equivalente al enmascarado que ya usa
`core/services/whatsapp_credential_service.py:_mask_token` para mostrar
credenciales en la UI — los logs de éxito de envío (`messaging/sender.py`)
imprimían el teléfono normalizado completo.

No son secretos per se (el teléfono ya es visible en la conversación de
WhatsApp), pero son dato personal — se redactan por política uniforme de
logging, no porque el valor en sí sea sensible como un token.
"""
from __future__ import annotations


def redact_phone(phone: str) -> str:
    """Conserva los últimos 4 dígitos, enmascara el resto (ej. `***4567`)."""
    if not phone:
        return "***"
    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if len(digits_only) < 4:
        return "***"
    return "***" + digits_only[-4:]


def redact_secret(value: str) -> str:
    """Enmascara un secreto/token: primeros 4 + relleno + últimos 4.

    Mismo patrón que `core/services/whatsapp_credential_service.py:
    _mask_token` — se mantiene consistente con `SecretStore.mask` en
    `infrastructure/secrets/secret_store.py`.
    """
    if not value or len(value) < 8:
        return "***"
    return value[:4] + "*" * (len(value) - 8) + value[-4:]
