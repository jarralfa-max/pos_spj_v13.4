# domain/whatsapp/value_objects/phone_number.py — WA-2
"""
Value object inmutable para un número E.164 del canal WhatsApp.

Envuelve — NO duplica — el único normalizador de teléfonos del proyecto
(`domain/phone_number.py::normalize_to_e164`, regla del prompt maestro §13:
"una sola normalización de teléfonos", ya usado por `erp/bridge.py` y
`erp/adjustment_approval.py`). Este value object solo agrega inmutabilidad
y validación en el borde del dominio — un `WhatsAppPhoneNumber` que existe
siempre es E.164 válido, o la construcción falla.
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.phone_number import normalize_to_e164
from domain.whatsapp.exceptions import InvalidPhoneNumberError


@dataclass(frozen=True)
class WhatsAppPhoneNumber:
    """Número de teléfono canónico E.164, p. ej. `+525512345678`."""

    value: str

    @classmethod
    def from_raw(cls, raw: str, default_country: str = "MX") -> "WhatsAppPhoneNumber":
        if not raw or not str(raw).strip():
            raise InvalidPhoneNumberError("Número de teléfono vacío")
        normalized = normalize_to_e164(raw, default_country=default_country)
        if not normalized or not normalized.startswith("+"):
            raise InvalidPhoneNumberError(f"No se pudo normalizar el número: {raw!r}")
        return cls(value=normalized)

    def __str__(self) -> str:
        return self.value
