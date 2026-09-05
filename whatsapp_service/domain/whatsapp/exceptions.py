# domain/whatsapp/exceptions.py — Excepciones de dominio (WA-2)
"""
Solo las excepciones necesarias para las entidades construidas en WA-2
(Accounts, Numbers, Identity, Conversation, Message). El catálogo completo
del prompt maestro (§73 — p.ej. `WhatsAppAccountNotFoundError`,
`ProviderUnavailableError`, `ConsentRequiredError`) pertenece mayormente a
la capa de aplicación/repositorios (fases WA-4, WA-9, WA-16...) y se agrega
incrementalmente en cada fase que realmente las necesita, no todas de una
vez por adelantado.
"""
from __future__ import annotations


class WhatsAppDomainError(Exception):
    """Base de toda excepción de dominio del canal WhatsApp."""


class InvalidPhoneNumberError(WhatsAppDomainError):
    """El valor no pudo normalizarse a un E.164 válido."""


class InvalidChannelNumberStateError(WhatsAppDomainError):
    """Transición de estado inválida para `WhatsAppChannelNumber`."""


class InvalidConversationStateTransitionError(WhatsAppDomainError):
    """Transición de estado inválida para `WhatsAppConversation`."""


class InvalidConversationContextError(WhatsAppDomainError):
    """El contexto conversacional no cumple su esquema versionado."""


class InvalidMessageDeliveryTransitionError(WhatsAppDomainError):
    """Transición de estado inválida para `WhatsAppMessageDelivery`."""


class InvalidInboxJobTransitionError(WhatsAppDomainError):
    """Transición de estado inválida para `InboundMessageJob` (WA-6)."""


class ChannelNumberNotRegisteredError(WhatsAppDomainError):
    """El `phone_number_id` del webhook no corresponde a ningún
    `WhatsAppChannelNumber` registrado (WA-6). El número debe darse de alta
    (Accounts/Numbers — administración, fuera de alcance de WA-6) antes de
    que el webhook pueda procesar mensajes reales para él."""
