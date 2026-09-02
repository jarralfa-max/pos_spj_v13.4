# domain/whatsapp/enums.py — Vocabularios cerrados del dominio (WA-2)
"""
Enumeraciones descritas en el prompt maestro §10-15. Ningún otro módulo del
canal WhatsApp debe redefinir estos valores — son la única fuente de verdad
para cuentas, números, identidad, conversaciones y mensajes.
"""
from __future__ import annotations

from enum import Enum


class WhatsAppProvider(str, Enum):
    META = "META"
    TWILIO = "TWILIO"


class AccountStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    DISCONNECTED = "DISCONNECTED"
    RETIRED = "RETIRED"


class ChannelNumberStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    DISCONNECTED = "DISCONNECTED"
    RETIRED = "RETIRED"


class ChannelRole(str, Enum):
    GLOBAL_CUSTOMER_SERVICE = "GLOBAL_CUSTOMER_SERVICE"
    BRANCH_SALES = "BRANCH_SALES"
    BRANCH_ORDERS = "BRANCH_ORDERS"
    DELIVERY = "DELIVERY"
    INTERNAL_OPERATIONS = "INTERNAL_OPERATIONS"
    MARKETING = "MARKETING"


class IdentityStatus(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    MERGED = "MERGED"


class ConversationState(str, Enum):
    OPEN = "OPEN"
    BOT_ACTIVE = "BOT_ACTIVE"
    WAITING_CUSTOMER = "WAITING_CUSTOMER"
    WAITING_ERP = "WAITING_ERP"
    WAITING_PAYMENT = "WAITING_PAYMENT"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    HANDOFF_REQUESTED = "HANDOFF_REQUESTED"
    HUMAN_ACTIVE = "HUMAN_ACTIVE"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


# Una conversación en uno de estos estados no puede volver a abrirse in-place
# (WA-2, invariante mínimo de la entidad). La máquina de estados completa
# — quién decide la siguiente transición según intención/timeout — es
# responsabilidad de WA-7 (Conversation Engine), no de esta capa.
TERMINAL_CONVERSATION_STATES = frozenset({
    ConversationState.RESOLVED,
    ConversationState.CLOSED,
    ConversationState.EXPIRED,
    ConversationState.BLOCKED,
})


class MessageDirection(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    INTERNAL = "INTERNAL"


class MessageType(str, Enum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    DOCUMENT = "DOCUMENT"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    LOCATION = "LOCATION"
    CONTACT = "CONTACT"
    INTERACTIVE = "INTERACTIVE"
    BUTTON_REPLY = "BUTTON_REPLY"
    LIST_REPLY = "LIST_REPLY"
    TEMPLATE = "TEMPLATE"
    REACTION = "REACTION"
    SYSTEM = "SYSTEM"


class MessageDeliveryStatus(str, Enum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


TERMINAL_DELIVERY_STATUSES = frozenset({
    MessageDeliveryStatus.DELIVERED,
    MessageDeliveryStatus.READ,
    MessageDeliveryStatus.DEAD_LETTER,
    MessageDeliveryStatus.CANCELLED,
})
