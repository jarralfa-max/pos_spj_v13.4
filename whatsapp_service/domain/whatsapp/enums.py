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


class Intent(str, Enum):
    """Catálogo de intenciones (§27 del prompt maestro) — vocabulario
    compartido entre el resolvedor de intención (WA-8) y el motor
    conversacional (WA-7, que decide transición de estado a partir de una
    intención ya resuelta, no la resuelve él mismo)."""

    GREETING = "GREETING"
    SHOW_MENU = "SHOW_MENU"
    SELECT_BRANCH = "SELECT_BRANCH"
    SEARCH_PRODUCT = "SEARCH_PRODUCT"
    CHECK_PRICE = "CHECK_PRICE"
    CHECK_STOCK = "CHECK_STOCK"
    CREATE_ORDER = "CREATE_ORDER"
    UPDATE_ORDER = "UPDATE_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    CREATE_QUOTE = "CREATE_QUOTE"
    ACCEPT_QUOTE = "ACCEPT_QUOTE"
    REJECT_QUOTE = "REJECT_QUOTE"
    PAY_ORDER = "PAY_ORDER"
    CHECK_ORDER_STATUS = "CHECK_ORDER_STATUS"
    SCHEDULE_DELIVERY = "SCHEDULE_DELIVERY"
    TRACK_DELIVERY = "TRACK_DELIVERY"
    REGISTER_CUSTOMER = "REGISTER_CUSTOMER"
    UPDATE_ADDRESS = "UPDATE_ADDRESS"
    CHECK_LOYALTY = "CHECK_LOYALTY"
    SHOW_DIGITAL_CARD = "SHOW_DIGITAL_CARD"
    CHECK_COUPON = "CHECK_COUPON"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    OPT_OUT = "OPT_OUT"
    HELP = "HELP"
    UNKNOWN = "UNKNOWN"


class ConversationSignal(str, Enum):
    """WA-7 — señales que mueven el estado de una conversación. Distinto
    del catálogo de `Intent`: una señal es "qué pasó" a nivel de
    conversación (el bot respondió, se requiere aprobación, un agente se
    unió...), no "qué quiere el cliente". Varias intenciones de negocio
    pueden producir la misma señal (p. ej. CREATE_ORDER y CREATE_QUOTE
    ambas pueden terminar en `BOT_RESPONDED` si el bot completó la
    respuesta en un solo turno)."""

    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    BOT_RESPONDED = "BOT_RESPONDED"
    AWAITING_ERP_CONFIRMATION = "AWAITING_ERP_CONFIRMATION"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    HANDOFF_REQUESTED = "HANDOFF_REQUESTED"
    AGENT_JOINED = "AGENT_JOINED"
    RESOLVED = "RESOLVED"
    TIMEOUT = "TIMEOUT"
    RESET = "RESET"
    BLOCK = "BLOCK"


class InboxStatus(str, Enum):
    """§20-21 del prompt maestro — estado de un job de procesamiento de
    mensaje entrante (WA-6)."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY = "RETRY"
    DEAD_LETTER = "DEAD_LETTER"


TERMINAL_INBOX_STATUSES = frozenset({
    InboxStatus.COMPLETED,
    InboxStatus.DEAD_LETTER,
})


class DeliveryMethod(str, Enum):
    """WA-10 — §35 del prompt maestro."""

    PICKUP = "PICKUP"
    DELIVERY = "DELIVERY"


class OrderDraftStatus(str, Enum):
    """WA-10 — el borrador conversacional NUNCA es el pedido canónico
    (§34) — este estado es propio del canal, no del pedido en el ERP."""

    BUILDING = "BUILDING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


TERMINAL_ORDER_DRAFT_STATUSES = frozenset({
    OrderDraftStatus.CONFIRMED,
    OrderDraftStatus.CANCELLED,
})


class IdempotencyStatus(str, Enum):
    """WA-10 — §19 del prompt maestro."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class QuoteDraftStatus(str, Enum):
    """WA-11 — §37 del prompt maestro. A diferencia de `OrderDraft`
    (confirmar == crear en un paso), una cotización se CREA en el ERP
    (obtiene folio+vigencia) y solo DESPUÉS se acepta/rechaza — dos pasos
    con estados intermedios propios."""

    CAPTURING = "CAPTURING"
    CREATED = "CREATED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


TERMINAL_QUOTE_DRAFT_STATUSES = frozenset({
    QuoteDraftStatus.ACCEPTED,
    QuoteDraftStatus.REJECTED,
    QuoteDraftStatus.EXPIRED,
})


class DeliveryRequestStatus(str, Enum):
    """WA-13 — el pedido conversacional ya fue confirmado (WA-10); esto
    solo rastrea si el canal logró programar la entrega en el ERP
    (`DeliveryApiClient.schedule`, WA-9). No es el estado operativo real
    de la entrega (recolección/en ruta/entregado) — eso lo posee el
    bounded context Orders/Delivery (ver `orders_delivery_enterprise_transformation`),
    no WhatsApp."""

    REQUESTED = "REQUESTED"
    SCHEDULED = "SCHEDULED"
    FAILED = "FAILED"


TERMINAL_DELIVERY_REQUEST_STATUSES = frozenset({
    DeliveryRequestStatus.SCHEDULED,
    DeliveryRequestStatus.FAILED,
})


class ConsentAction(str, Enum):
    """WA-14 — qué se le pidió al puerto de consentimiento, para el
    registro/testeo de `ConsentService`; no es un valor persistido (el
    estado real vive en `ConsentStatus`, del bounded context Customer
    Privacy, reutilizado tal cual, no reinventado aquí)."""

    GRANT = "GRANT"
    WITHDRAW = "WITHDRAW"


class HandoffStatus(str, Enum):
    """WA-16 — ciclo de vida de una solicitud de traspaso a humano."""

    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


TERMINAL_HANDOFF_STATUSES = frozenset({
    HandoffStatus.RESOLVED,
    HandoffStatus.CANCELLED,
})


class OutboxMessageStatus(str, Enum):
    """WA-17 — refleja 1:1 el campo `status` de `whatsapp_outbox` (WA-3,
    §21-22)."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


TERMINAL_OUTBOX_STATUSES = frozenset({
    OutboxMessageStatus.SENT,
    OutboxMessageStatus.DEAD_LETTER,
})
