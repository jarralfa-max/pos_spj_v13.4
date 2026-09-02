"""Closed Pedidos/Delivery domain catalogs (master prompt §6-8, §14-15).

ORD-2 scope: only the Order-side enums a pure `CustomerOrder` aggregate needs.
Delivery-side catalogs (DeliveryJob status, DeliveryAssignment status, driver
status, route status, etc. — §32-35) are added in ORD-15+ once the separate
`DeliveryJob` aggregate is built — master prompt §5 is explicit that Order and
Delivery must not be modeled as one fused status.
"""

from __future__ import annotations

from enum import Enum


class OrderChannel(str, Enum):
    """§6: the channel determines origin, experience, notification rules and
    deduplication — never a second parallel order table per channel."""

    POS = "POS"
    WHATSAPP = "WHATSAPP"
    COUNTER = "COUNTER"
    PHONE = "PHONE"
    E_COMMERCE = "E_COMMERCE"
    MOBILE_APP_FUTURE = "MOBILE_APP_FUTURE"
    SALES_REP = "SALES_REP"
    BACKOFFICE = "BACKOFFICE"
    API = "API"
    IMPORT = "IMPORT"
    MARKETPLACE_FUTURE = "MARKETPLACE_FUTURE"


class FulfillmentType(str, Enum):
    """§7: the fulfillment modality determines whether an address/driver/
    route is required, and which workflow/SLA applies."""

    COUNTER = "COUNTER"
    PICKUP = "PICKUP"
    CURBSIDE_FUTURE = "CURBSIDE_FUTURE"
    HOME_DELIVERY = "HOME_DELIVERY"
    BRANCH_DELIVERY = "BRANCH_DELIVERY"
    WHOLESALE_DELIVERY = "WHOLESALE_DELIVERY"
    SCHEDULED_DELIVERY = "SCHEDULED_DELIVERY"
    EXPRESS_DELIVERY = "EXPRESS_DELIVERY"
    ROUTE_DELIVERY = "ROUTE_DELIVERY"
    THIRD_PARTY_DELIVERY_FUTURE = "THIRD_PARTY_DELIVERY_FUTURE"


class OrderType(str, Enum):
    """§8."""

    STANDARD = "STANDARD"
    SCHEDULED = "SCHEDULED"
    EXPRESS = "EXPRESS"
    WHOLESALE = "WHOLESALE"
    QUOTE_CONVERTED = "QUOTE_CONVERTED"
    CUSTOMER_ORDER = "CUSTOMER_ORDER"
    RECURRING_FUTURE = "RECURRING_FUTURE"
    SUBSCRIPTION_FUTURE = "SUBSCRIPTION_FUTURE"
    REPLACEMENT = "REPLACEMENT"
    REDELIVERY = "REDELIVERY"
    RETURN_PICKUP = "RETURN_PICKUP"


class OrderStatus(str, Enum):
    """§15 "Order status" — the coarse commercial-commitment lifecycle a pure
    `CustomerOrder` aggregate owns. Deliberately NOT the same enum as §14's
    full canonical status list (DRAFT..REVERSED) — that longer list mixes
    order/fulfillment/payment/approval concerns together, which §15 itself
    says never to do. Fine-grained fulfillment state lives in
    `FulfillmentStatus` below; delivery-specific state lives in a future
    `DeliveryStatus` (ORD-15)."""

    DRAFT = "DRAFT"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    IN_FULFILLMENT = "IN_FULFILLMENT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"
    REVERSED = "REVERSED"


class FulfillmentStatus(str, Enum):
    """§15."""

    PENDING = "PENDING"
    RESERVED = "RESERVED"
    PREPARING = "PREPARING"
    READY = "READY"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RETURNED = "RETURNED"


class PaymentStatus(str, Enum):
    """§15."""

    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    AUTHORIZED = "AUTHORIZED"
    PENDING_CASH_ON_DELIVERY = "PENDING_CASH_ON_DELIVERY"
    CREDIT_APPROVED = "CREDIT_APPROVED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class CustomerApprovalStatus(str, Enum):
    """§15."""

    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ScheduleStatus(str, Enum):
    """§19: a scheduled order's own activation lifecycle, independent of
    `OrderStatus` — a SCHEDULED order sits CONFIRMED (or even DRAFT) while
    its schedule is merely SCHEDULED/ACTIVATION_PENDING; activation is what
    moves it into normal fulfillment."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    SCHEDULED = "SCHEDULED"
    ACTIVATION_PENDING = "ACTIVATION_PENDING"
    ACTIVATED = "ACTIVATED"
    RESCHEDULED = "RESCHEDULED"
    CANCELLED = "CANCELLED"
    MISSED = "MISSED"


class GeocodingStatus(str, Enum):
    """§20: geocoding must never block an order when a manual address is
    already sufficient — a status, not a gate."""

    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    GEOCODED = "GEOCODED"
    MANUAL = "MANUAL"
    FAILED = "FAILED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class PreparationStatus(str, Enum):
    """§25: preparation's own lifecycle, independent of `FulfillmentStatus`
    (which only tracks the coarse PENDING/PREPARING/READY view)."""

    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    PARTIALLY_PREPARED = "PARTIALLY_PREPARED"
    PENDING_WEIGHT = "PENDING_WEIGHT"
    PENDING_CUSTOMER_APPROVAL = "PENDING_CUSTOMER_APPROVAL"
    READY = "READY"
    CANCELLED = "CANCELLED"


class SubstitutionType(str, Enum):
    """§28."""

    SAME_PRODUCT_DIFFERENT_PRESENTATION = "SAME_PRODUCT_DIFFERENT_PRESENTATION"
    EQUIVALENT_PRODUCT = "EQUIVALENT_PRODUCT"
    CUSTOMER_APPROVED_ALTERNATIVE = "CUSTOMER_APPROVED_ALTERNATIVE"
    NO_SUBSTITUTION = "NO_SUBSTITUTION"


class PackageType(str, Enum):
    """§29."""

    BAG = "BAG"
    BOX = "BOX"
    INSULATED_BOX = "INSULATED_BOX"
    COOLER = "COOLER"
    CRATE = "CRATE"
    TRAY = "TRAY"
    OTHER = "OTHER"


class PackageStatus(str, Enum):
    OPEN = "OPEN"
    SEALED = "SEALED"
    CANCELLED = "CANCELLED"


class DeliveryStatus(str, Enum):
    """§32: `DeliveryJob`'s own lifecycle — entirely separate from
    `OrderStatus`/`FulfillmentStatus` (master prompt §5: Order ≠ Delivery).
    ORD-15 only builds the CREATE/ASSIGN transitions; DISPATCHED onward are
    ORD-16-19's use cases, reusing this same enum/policy."""

    PENDING_ASSIGNMENT = "PENDING_ASSIGNMENT"
    ASSIGNED = "ASSIGNED"
    READY_TO_DISPATCH = "READY_TO_DISPATCH"
    DISPATCHED = "DISPATCHED"
    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED = "ARRIVED"
    DELIVERY_ATTEMPT = "DELIVERY_ATTEMPT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    REDELIVERY_PENDING = "REDELIVERY_PENDING"
    RETURNING = "RETURNING"
    RETURNED_TO_BRANCH = "RETURNED_TO_BRANCH"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class AssignmentStatus(str, Enum):
    """§33."""

    PROPOSED = "PROPOSED"
    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class RouteStatus(str, Enum):
    """§35."""

    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    ASSIGNED = "ASSIGNED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class RouteStopStatus(str, Enum):
    PENDING = "PENDING"
    ARRIVED = "ARRIVED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


class FailureReason(str, Enum):
    """§40: the closed catalog a failed `DeliveryAttempt.failure_reason`
    must belong to."""

    CUSTOMER_NOT_HOME = "CUSTOMER_NOT_HOME"
    ADDRESS_NOT_FOUND = "ADDRESS_NOT_FOUND"
    CUSTOMER_REJECTED = "CUSTOMER_REJECTED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PRODUCT_DAMAGED = "PRODUCT_DAMAGED"
    TEMPERATURE_FAILURE = "TEMPERATURE_FAILURE"
    SECURITY_RISK = "SECURITY_RISK"
    VEHICLE_FAILURE = "VEHICLE_FAILURE"
    WRONG_ADDRESS = "WRONG_ADDRESS"
    CONTACT_UNAVAILABLE = "CONTACT_UNAVAILABLE"
    OTHER = "OTHER"


class RedeliveryStatus(str, Enum):
    """§41."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class CollectionPaymentMethod(str, Enum):
    """§44: cash-on-delivery collection methods. Distinct from
    `PaymentStatus` (the order's own coarse paid/unpaid view, §15) — this is
    HOW the money was collected at the door."""

    CASH = "CASH"
    CARD_TERMINAL = "CARD_TERMINAL"
    TRANSFER = "TRANSFER"
    PAYMENT_LINK = "PAYMENT_LINK"
    MIXED = "MIXED"
    CREDIT = "CREDIT"
    PREPAID = "PREPAID"


class CollectionStatus(str, Enum):
    """§45."""

    EXPECTED = "EXPECTED"
    COLLECTED = "COLLECTED"
    PARTIALLY_COLLECTED = "PARTIALLY_COLLECTED"
    FAILED = "FAILED"
    PENDING_SETTLEMENT = "PENDING_SETTLEMENT"
    SETTLED = "SETTLED"
    DISPUTED = "DISPUTED"


class SettlementStatus(str, Enum):
    """§46."""

    OPEN = "OPEN"
    PENDING_REVIEW = "PENDING_REVIEW"
    BALANCED = "BALANCED"
    WITH_DIFFERENCE = "WITH_DIFFERENCE"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    CLOSED = "CLOSED"


class OrderLineStatus(str, Enum):
    """§12: a `CustomerOrderLine`'s own status, independent of the order's
    aggregate-level `OrderStatus`/`FulfillmentStatus` (a single line can be
    substituted/rejected while its sibling lines stay on the happy path)."""

    PENDING = "PENDING"
    RESERVED = "RESERVED"
    PREPARING = "PREPARING"
    PREPARED = "PREPARED"
    PENDING_CUSTOMER_APPROVAL = "PENDING_CUSTOMER_APPROVAL"
    SUBSTITUTED = "SUBSTITUTED"
    REJECTED = "REJECTED"
    READY = "READY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
