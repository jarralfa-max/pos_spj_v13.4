"""Domain exceptions for the Pedidos/Delivery (Order Management + Last-Mile
Fulfillment) bounded context.

ORD-1 defines the security-related errors (permission, configuration, hot
authorization, segregation of duties) for the whole "Pedidos y Delivery" area
— order capture/confirmation/scheduling, preparation, catch-weight
adjustment, customer approval, substitution, packaging, driver assignment,
routing, dispatch, delivery, failed-delivery/redelivery, cash-on-delivery
collection and driver settlement (master prompt §63: they all share one nav
entry/permission catalog key, ``DELIVERY``).

ORD-2 adds the operational errors the `CustomerOrder`/`CustomerOrderLine`
aggregate and its policies raise (a subset of master prompt §74 — only the
ones a pure domain layer can detect without I/O; reservation/geocoding/
payment/delivery errors belong to later phases that touch other bounded
contexts or the separate `DeliveryJob` aggregate, ORD-15+).

Mirrors ``backend/domain/sales/exceptions.py``'s own SALES-2/3-equivalent
phases exactly.
"""

from __future__ import annotations


class OrdersDeliveryDomainError(Exception):
    """Base for Pedidos/Delivery rule violations."""


class OrdersDeliveryPermissionDeniedError(OrdersDeliveryDomainError):
    """The user lacks the granular permission the action requires."""


class OrdersDeliveryConfigurationError(OrdersDeliveryDomainError):
    """A security-sensitive component was built without its mandatory
    wiring (e.g. an authorization policy with no PermissionChecker). Fail
    closed: never allow an operation to proceed on an unconfigured
    authorization gate."""


class OrdersDeliverySegregationOfDutiesError(OrdersDeliveryDomainError):
    """A hot authorization/approval was attempted by the same user who
    requested it — a second pair of eyes is mandatory (master prompt §64/§65:
    'quien asigna repartidor no debe liquidar efectivo', 'quien revierte una
    entrega requiere autorización independiente')."""


class InvalidOrdersDeliveryAuditFieldError(OrdersDeliveryDomainError):
    """A required audit/authorization field is missing or of the wrong
    type (e.g. a float where Decimal is required)."""


# ── ORD-2: operational errors (master prompt §74, domain-detectable subset) ──

class OrderNotFoundError(OrdersDeliveryDomainError):
    """No CustomerOrder with the given id exists (master prompt §74)."""


class OrderLineNotFoundError(OrdersDeliveryDomainError):
    """No line with the given id exists on this CustomerOrder."""


class InvalidOrderStateError(OrdersDeliveryDomainError):
    """The requested transition/mutation is not valid for the order's
    current `OrderStatus` (`OrderInvalidStatusError` in the master prompt's
    vocabulary, §74)."""


class OrderConfirmationRequiredError(OrdersDeliveryDomainError):
    """An operation that requires a CONFIRMED order (reservation,
    preparation) was attempted against a DRAFT/PENDING_CONFIRMATION one."""


class OrderEmptyError(OrdersDeliveryDomainError):
    """An operation that requires at least one line (confirm) was attempted
    on a CustomerOrder with none."""


class OrderCancellationNotAllowedError(OrdersDeliveryDomainError):
    """A CustomerOrder cannot be cancelled from its current status — master
    prompt §42 distinguishes cancellation before dispatch from a reversal
    after delivery."""


class InvalidOrderQuantityError(OrdersDeliveryDomainError):
    """A requested/prepared/final quantity or weight is missing,
    non-Decimal, zero or negative where a positive value is required."""


class InvalidOrderMoneyError(OrdersDeliveryDomainError):
    """A monetary value is missing, non-Decimal, or otherwise invalid
    (negative where not allowed, infinite, NaN)."""


class DuplicateOperationError(OrdersDeliveryDomainError):
    """An operation was attempted with an ``operation_id`` that has already
    been used — idempotency guard (master prompt §58)."""


# ── ORD-6: scheduled orders (master prompt §19) ──────────────────────────

class InvalidOrderScheduleError(OrdersDeliveryDomainError):
    """A schedule's window/activation fields are missing, out of order
    (window_end before window_start), or the requested transition is not
    valid for the order's current `ScheduleStatus`."""


class OrderActivationNotDueError(OrdersDeliveryDomainError):
    """`ActivateScheduledOrderUseCase` was called before the schedule's
    `activation_at` — master prompt §19: activation must consider lead
    time, not fire early on a manual/impatient trigger."""


# ── ORD-7: addresses and delivery zones (master prompt §20-22) ──────────

class InvalidAddressError(OrdersDeliveryDomainError):
    """A delivery address is missing required fields, or a manual address
    is being marked geocoded/failed without ever having been requested."""


class DeliveryAddressRequiredError(OrdersDeliveryDomainError):
    """A `HOME_DELIVERY`/`BRANCH_DELIVERY`/... fulfillment type requires a
    delivery address, and the order has none attached (master prompt §20)."""


class DeliveryZoneNotAvailableError(OrdersDeliveryDomainError):
    """No active `DeliveryZone` covers the given postal code/branch, or the
    order total is below the zone's minimum order (master prompt §21-22)."""


# ── ORD-8: inventory (master prompt §23-24) ──────────────────────────────

class OrderInventoryReservationFailedError(OrdersDeliveryDomainError):
    """Inventory could not reserve/release stock for this order (insufficient
    stock, unknown reservation, or the reservation is no longer active) —
    mirrors `backend/domain/sales/exceptions.py::InventoryReservationFailedError`."""


# ── ORD-9: preparation (master prompt §25) ───────────────────────────────

class OrderPreparationNotAllowedError(OrdersDeliveryDomainError):
    """The requested preparation transition (assign/start/complete/cancel)
    is not valid for the order's current `PreparationStatus`/`OrderStatus`
    (master prompt §74's own named error)."""


# ── ORD-10: catch-weight adjustment (master prompt §26-27) ───────────────

class CustomerApprovalRequiredError(OrdersDeliveryDomainError):
    """An operation that requires a resolved customer approval (dispatch,
    finalize) was attempted while a line still sits PENDING_CUSTOMER_APPROVAL
    (master prompt §74's own named error)."""


class CustomerApprovalExpiredError(OrdersDeliveryDomainError):
    """A customer's accept/reject decision was recorded after the approval
    window expired (master prompt §74's own named error)."""


class ApprovalExpirationNotDueError(OrdersDeliveryDomainError):
    """`ExpireCustomerApprovalUseCase` was called before
    `customer_approval_expires_at` — mirrors `OrderActivationNotDueError`'s
    reasoning (ORD-6): expiration must consider the real deadline, not fire
    early on a manual/impatient trigger."""


# ── ORD-12: substitutions (master prompt §28-29) ─────────────────────────

class SubstitutionNotAllowedError(OrdersDeliveryDomainError):
    """A substitution was proposed for a line with `substitution_allowed`
    False, or the requested transition is not valid for the line's current
    status (master prompt §74's own named error)."""


# ── ORD-13: packaging (master prompt §29) ────────────────────────────────

class InvalidPackageError(OrdersDeliveryDomainError):
    """A package's fields are invalid (no lines, non-positive weight) or the
    requested transition is not valid for its current `PackageStatus`."""


# ── ORD-14: pickup/counter (master prompt §30) ───────────────────────────

class PickupVerificationFailedError(OrdersDeliveryDomainError):
    """The code/identity presented at the counter does not match the order's
    `pickup_verification_code`."""


class PaymentRequiredForPickupError(OrdersDeliveryDomainError):
    """A pickup/counter order cannot be handed over while `payment_status`
    is not `PAID` (master prompt §30: "Cobro si pendiente" happens before
    hand-over, never after)."""


# ── ORD-15: DeliveryJob (master prompt §31-32) ───────────────────────────

class DeliveryJobNotFoundError(OrdersDeliveryDomainError):
    """No DeliveryJob with the given id exists."""


class InvalidDeliveryJobStateError(OrdersDeliveryDomainError):
    """The requested transition is not valid for the delivery job's current
    `DeliveryStatus` (master prompt §74's own named error)."""


class DeliveryDriverRequiredError(OrdersDeliveryDomainError):
    """A transition that requires an assigned driver (dispatch) was
    attempted on a job with no `assigned_driver_id` (master prompt §74's own
    named error)."""


# ── ORD-16: drivers (master prompt §33-34) ───────────────────────────────

class DriverNotAvailableError(OrdersDeliveryDomainError):
    """The driver's operational profile is inactive, or already at its
    concurrent-assignment capacity — never assign beyond what §34's own
    profile allows."""


class InvalidAssignmentStateError(OrdersDeliveryDomainError):
    """The requested transition is not valid for the assignment's current
    `AssignmentStatus`."""


class AssignmentNotFoundError(OrdersDeliveryDomainError):
    """No DeliveryAssignment with the given id exists."""


class DriverProfileNotFoundError(OrdersDeliveryDomainError):
    """No DriverOperationalProfile exists for the given driver_id."""


# ── ORD-17: routes (master prompt §35) ────────────────────────────────────

class RouteNotFoundError(OrdersDeliveryDomainError):
    """No DeliveryRoute with the given id exists."""


class InvalidRouteStateError(OrdersDeliveryDomainError):
    """The requested transition is not valid for the route's current
    `RouteStatus`."""


class InvalidRouteStopError(OrdersDeliveryDomainError):
    """A stop's fields are invalid (duplicate sequence, no delivery job) or
    the route cannot accept new stops in its current status."""


# ── ORD-18: dispatch and delivery (master prompt §36-38) ─────────────────

class DispatchNotAllowedError(OrdersDeliveryDomainError):
    """A precondition for dispatch is not met (order not ready, pending
    customer approval, no driver assigned) — master prompt §36's own
    pre-dispatch checklist."""


class DeliveryEvidenceRequiredError(OrdersDeliveryDomainError):
    """A successful delivery attempt was recorded without the evidence the
    policy requires (master prompt §38, §74's own named error)."""


class DeliveryFailureReasonRequiredError(OrdersDeliveryDomainError):
    """A failed delivery attempt was recorded without a reason (master
    prompt §40's own closed catalog of failure reasons)."""


# ── ORD-19: failed deliveries and redelivery (master prompt §40-41) ──────

class InvalidRedeliveryStateError(OrdersDeliveryDomainError):
    """The requested transition is not valid for the redelivery request's
    current `RedeliveryStatus`."""


class RedeliveryNotAllowedError(OrdersDeliveryDomainError):
    """A redelivery was requested against a `DeliveryJob` that isn't
    `FAILED`, or the original job doesn't exist."""


class RedeliveryRequestNotFoundError(OrdersDeliveryDomainError):
    """No RedeliveryRequest with the given id exists."""


# ── ORD-20: cash on delivery (master prompt §44-45) ──────────────────────

class InvalidCashCollectionError(OrdersDeliveryDomainError):
    """A collection's amount is invalid (negative, or the requested
    transition is not valid for its current `CollectionStatus`)."""


class CashCollectionNotFoundError(OrdersDeliveryDomainError):
    """No DriverCashCollection with the given id/delivery_job_id exists."""


# ── ORD-21: driver settlement (master prompt §46) ────────────────────────

class InvalidSettlementStateError(OrdersDeliveryDomainError):
    """The requested transition is not valid for the settlement's current
    `SettlementStatus`."""


class SettlementRequiresCollectionsError(OrdersDeliveryDomainError):
    """A settlement was created with no `DriverCashCollection`s to
    reconcile."""


class SettlementNotFoundError(OrdersDeliveryDomainError):
    """No DriverSettlement with the given id exists."""


# ── ORD-22: sales and finance integration (master prompt §22) ────────────

class SaleProjectionFailedError(OrdersDeliveryDomainError):
    """Projecting a `CustomerOrder` into a commercial `Sale` (Sales bounded
    context) failed — Sales rejected the start/line/payment/checkout call."""


class OrderAlreadyLinkedToSaleError(OrdersDeliveryDomainError):
    """An order already has a different `sale_id`; linking is idempotent for
    the SAME sale but must never silently overwrite an existing link."""


class OrderNotLinkedToSaleError(OrdersDeliveryDomainError):
    """A payment or refund was requested for an order that has not yet been
    projected into a Sale."""


class InvalidPaymentStatusError(OrdersDeliveryDomainError):
    """The requested transition is not valid for the order's current
    `PaymentStatus`."""


class RefundNotAllowedError(OrdersDeliveryDomainError):
    """An order can only be reversed/refunded from `COMPLETED` (master
    prompt §43 "ReverseDeliveredOrder") with money actually collected."""
