"""ORD-2 aggregate: CustomerOrder (aggregate root) and CustomerOrderLine
(owned entity). Mirrors backend/domain/sales/entities.py's `Sale`/`SaleLine`
shape exactly: `slots=True` dataclasses, `new_uuid()`/`validate_uuidv7()` for
identity, classmethod factories, mutation methods that delegate to policies
before touching state.

Master prompt §5: a CustomerOrder is the customer's operational commitment,
distinct from a Sale (the fiscal/commercial document) and a DeliveryJob (the
last-mile execution, ORD-15+) — this aggregate owns none of those, only its
own commitment state. CustomerOrder owns its lines and its own OrderTotals —
no caller ever assembles totals by hand (see
`backend/domain/orders_delivery/services/order_total_service.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.orders_delivery.enums import (
    CustomerApprovalStatus,
    FulfillmentStatus,
    FulfillmentType,
    OrderChannel,
    OrderLineStatus,
    OrderStatus,
    OrderType,
    PaymentStatus,
    PreparationStatus,
    ScheduleStatus,
    SubstitutionType,
)
from backend.domain.orders_delivery.exceptions import (
    ApprovalExpirationNotDueError,
    CustomerApprovalExpiredError,
    InvalidOrderQuantityError,
    InvalidOrderStateError,
    OrderAlreadyLinkedToSaleError,
    OrderLineNotFoundError,
    OrderNotFoundError,
    OrderPreparationNotAllowedError,
)
from backend.domain.orders_delivery.policies.order_lifecycle_policy import (
    OrderCancellationPolicy,
    OrderConfirmationPolicy,
    OrderLifecyclePolicy,
    OrderReservationRequiredPolicy,
)
from backend.domain.orders_delivery.policies.order_payment_policy import OrderPaymentPolicy
from backend.domain.orders_delivery.policies.pickup_policy import PickupPolicy
from backend.domain.orders_delivery.policies.preparation_policy import OrderPreparationPolicy
from backend.domain.orders_delivery.policies.scheduled_order_policy import ScheduledOrderPolicy
from backend.domain.orders_delivery.policies.substitution_policy import SubstitutionPolicy
from backend.domain.orders_delivery.services.order_total_service import OrderTotalsService
from backend.domain.orders_delivery.value_objects.order_money import money
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.domain.orders_delivery.value_objects.order_totals import OrderTotals
from backend.domain.orders_delivery.value_objects.weight_adjustment_evaluation import (
    WeightAdjustmentEvaluation,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ids(*values: str) -> None:
    for value in values:
        validate_uuidv7(value)


@dataclass(slots=True)
class CustomerOrderLine:
    id: str
    order_id: str
    product_id: str
    variant_id: str | None = None
    requested_quantity: OrderQuantity | None = None
    requested_weight: OrderQuantity | None = None
    prepared_quantity: OrderQuantity | None = None
    prepared_weight: OrderQuantity | None = None
    final_quantity: OrderQuantity | None = None
    final_weight: OrderQuantity | None = None
    unit_price_snapshot: Decimal = Decimal("0")
    discount_snapshot: Decimal = Decimal("0")
    tax_snapshot: Decimal = Decimal("0")
    catch_weight_enabled: bool = False
    substitution_allowed: bool = True
    substitution_type: SubstitutionType | None = None
    substitute_product_id: str | None = None
    substitution_reason: str | None = None
    pre_substitution_unit_price: Decimal | None = None
    proposed_substitution_unit_price: Decimal | None = None
    customer_notes: str | None = None
    preparation_notes: str | None = None
    status: OrderLineStatus = OrderLineStatus.PENDING
    inventory_reservation_id: str | None = None
    package_id: str | None = None
    product_snapshot: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, order_id: str, product_id: str, unit_price: Decimal,
        variant_id: str | None = None,
        requested_quantity: OrderQuantity | None = None,
        requested_weight: OrderQuantity | None = None,
        catch_weight_enabled: bool = False, substitution_allowed: bool = True,
        customer_notes: str | None = None,
        product_snapshot: Mapping[str, Any] | None = None,
    ) -> "CustomerOrderLine":
        _ids(order_id, product_id)
        if variant_id is not None:
            _ids(variant_id)
        if requested_quantity is None and requested_weight is None:
            raise InvalidOrderQuantityError(
                "La línea requiere cantidad y/o peso solicitado")
        return cls(
            id=new_uuid(), order_id=order_id, product_id=product_id,
            variant_id=variant_id,
            requested_quantity=requested_quantity, requested_weight=requested_weight,
            unit_price_snapshot=money(unit_price, allow_zero=True),
            catch_weight_enabled=catch_weight_enabled,
            substitution_allowed=substitution_allowed,
            customer_notes=customer_notes,
            product_snapshot=dict(product_snapshot or {}),
        )

    def _requested_base_quantity(self) -> Decimal:
        """The Decimal magnitude `requested_subtotal` is priced against:
        weight when catch-weight is enabled (§26 — the customer is billed on
        actual/estimated weight, not piece count), otherwise quantity."""
        if self.catch_weight_enabled and self.requested_weight is not None:
            return self.requested_weight.value
        if self.requested_quantity is not None:
            return self.requested_quantity.value
        return self.requested_weight.value if self.requested_weight is not None else Decimal("0")

    def _final_base_quantity(self) -> Decimal:
        if self.catch_weight_enabled and self.final_weight is not None:
            return self.final_weight.value
        if self.final_quantity is not None:
            return self.final_quantity.value
        if self.final_weight is not None:
            return self.final_weight.value
        return self._requested_base_quantity()

    @property
    def requested_subtotal(self) -> Decimal:
        """Derived, never stored — so it can never drift from
        requested_quantity/requested_weight/unit_price_snapshot/discount/tax
        (same reasoning as `SaleLine.line_total`)."""
        return (self._requested_base_quantity() * self.unit_price_snapshot
                - self.discount_snapshot + self.tax_snapshot)

    @property
    def final_subtotal(self) -> Decimal:
        """§26: once preparation records a final quantity/weight (post
        catch-weight adjustment/customer approval), the billable subtotal
        must be recomputed from it, never from the originally requested
        amount."""
        return (self._final_base_quantity() * self.unit_price_snapshot
                - self.discount_snapshot + self.tax_snapshot)

    def billable_quantity(self) -> Decimal:
        """§22: the Decimal magnitude Sale-projection bills against — same
        final-weight-when-catch-weight-else-final_quantity priority
        `final_subtotal` already uses internally, exposed publicly because
        `AddSaleLineUseCase` needs an actual quantity, not a derived
        subtotal."""
        return self._final_base_quantity()

    def billable_unit(self) -> str:
        """The unit that goes with `billable_quantity()` — same
        catch-weight-vs-piece priority, falling back to the requested-side
        value when nothing has been finalized yet (mirrors
        `_final_base_quantity()`'s own fallback to requested)."""
        if self.catch_weight_enabled and self.final_weight is not None:
            return self.final_weight.unit
        if self.final_quantity is not None:
            return self.final_quantity.unit
        if self.final_weight is not None:
            return self.final_weight.unit
        if self.catch_weight_enabled and self.requested_weight is not None:
            return self.requested_weight.unit
        if self.requested_quantity is not None:
            return self.requested_quantity.unit
        return self.requested_weight.unit if self.requested_weight is not None else "PZA"

    def apply_discount(self, discount_total: Decimal) -> None:
        self.discount_snapshot = money(discount_total)
        self.updated_at = _now()

    def apply_tax(self, tax_total: Decimal) -> None:
        self.tax_snapshot = money(tax_total)
        self.updated_at = _now()

    def mark_status(self, status: OrderLineStatus) -> None:
        self.status = status
        self.updated_at = _now()

    def record_prepared_amount(self, *, quantity: OrderQuantity | None = None,
                                weight: OrderQuantity | None = None) -> None:
        """§25/§26: records what was actually prepared. Only the catch-weight
        tolerance/customer-approval decision (ORD-10) decides whether this
        becomes the line's `final_*` amount — this method only ever writes
        `prepared_*`, never `final_*`."""
        if quantity is None and weight is None:
            raise InvalidOrderQuantityError(
                "Se requiere cantidad y/o peso preparado")
        if quantity is not None:
            self.prepared_quantity = quantity
        if weight is not None:
            self.prepared_weight = weight
        self.status = OrderLineStatus.PREPARED
        self.updated_at = _now()

    def apply_weight_evaluation(self, evaluation: WeightAdjustmentEvaluation) -> None:
        """§26-27: the single place a prepared amount becomes a `final_*`
        amount — either immediately (within tolerance) or after the
        customer accepts (see `accept_customer_adjustment`)."""
        if evaluation.within_tolerance:
            self._finalize_from_prepared()
        else:
            self.status = OrderLineStatus.PENDING_CUSTOMER_APPROVAL
        self.updated_at = _now()

    def accept_customer_adjustment(self) -> None:
        """§11 ORD-11 idempotency: a repeated accept on an already-finalized
        line (a duplicate WhatsApp tap, a webhook retry) is a no-op, not an
        error — only a line that never reached approval, or one already
        rejected, is a real conflict."""
        if self.status == OrderLineStatus.PREPARED:
            return
        if self.status != OrderLineStatus.PENDING_CUSTOMER_APPROVAL:
            raise InvalidOrderStateError(
                f"La línea no tiene un ajuste pendiente de aprobación (estado: {self.status.value})")
        self._finalize_from_prepared()
        self.updated_at = _now()

    def reject_customer_adjustment(self) -> None:
        if self.status == OrderLineStatus.REJECTED:
            return
        if self.status != OrderLineStatus.PENDING_CUSTOMER_APPROVAL:
            raise InvalidOrderStateError(
                f"La línea no tiene un ajuste pendiente de aprobación (estado: {self.status.value})")
        self.status = OrderLineStatus.REJECTED
        self.updated_at = _now()

    def _finalize_from_prepared(self) -> None:
        if self.prepared_quantity is not None:
            self.final_quantity = self.prepared_quantity
        if self.prepared_weight is not None:
            self.final_weight = self.prepared_weight
        self.status = OrderLineStatus.PREPARED

    def propose_substitution(
        self, *, substitute_product_id: str, substitution_type: SubstitutionType,
        new_unit_price: Decimal, reason: str,
    ) -> None:
        """§28-29: "no sustituir silenciosamente" — proposing never applies
        the substitute outright, only puts the line up for the customer's
        decision (`accept_substitution`/`reject_substitution`)."""
        SubstitutionPolicy.ensure_can_propose(
            substitution_allowed=self.substitution_allowed, status=self.status)
        SubstitutionPolicy.ensure_valid_type(substitution_type)
        _ids(substitute_product_id)
        self.substitute_product_id = substitute_product_id
        self.substitution_type = substitution_type
        self.substitution_reason = reason
        self.pre_substitution_unit_price = self.unit_price_snapshot
        self.proposed_substitution_unit_price = money(new_unit_price, allow_zero=True)
        self.status = OrderLineStatus.PENDING_CUSTOMER_APPROVAL
        self.updated_at = _now()

    def accept_substitution(self) -> None:
        if self.status == OrderLineStatus.SUBSTITUTED:
            return  # idempotent: already accepted
        if self.status != OrderLineStatus.PENDING_CUSTOMER_APPROVAL or self.substitute_product_id is None:
            raise InvalidOrderStateError(
                f"La línea no tiene una sustitución pendiente de aprobación (estado: {self.status.value})")
        self.unit_price_snapshot = self.proposed_substitution_unit_price
        self.status = OrderLineStatus.SUBSTITUTED
        self.updated_at = _now()

    def reject_substitution(self) -> None:
        if self.status == OrderLineStatus.REJECTED:
            return  # idempotent: already rejected
        if self.status != OrderLineStatus.PENDING_CUSTOMER_APPROVAL or self.substitute_product_id is None:
            raise InvalidOrderStateError(
                f"La línea no tiene una sustitución pendiente de aprobación (estado: {self.status.value})")
        self.status = OrderLineStatus.REJECTED
        self.updated_at = _now()

    def set_package(self, package_id: str) -> None:
        self.package_id = package_id
        self.updated_at = _now()

    def set_reservation(self, reservation_id: str) -> None:
        self.inventory_reservation_id = reservation_id
        self.status = OrderLineStatus.RESERVED
        self.updated_at = _now()

    def clear_reservation(self) -> None:
        self.inventory_reservation_id = None
        self.updated_at = _now()


@dataclass(slots=True)
class CustomerOrder:
    id: str
    branch_id: str
    channel: OrderChannel
    order_type: OrderType
    fulfillment_type: FulfillmentType
    order_number: str | None = None
    customer_id: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    delivery_address_id: str | None = None
    requested_delivery_window: str | None = None
    scheduled_for: str | None = None
    delivery_window_start: str | None = None
    delivery_window_end: str | None = None
    activation_at: str | None = None
    schedule_status: ScheduleStatus = ScheduleStatus.NOT_APPLICABLE
    preparation_status: PreparationStatus = PreparationStatus.PENDING
    assigned_to_user_id: str | None = None
    station_id: str | None = None
    preparation_started_at: str | None = None
    preparation_completed_at: str | None = None
    pickup_verification_code: str | None = None
    priority: str | None = None
    status: OrderStatus = OrderStatus.DRAFT
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    fulfillment_status: FulfillmentStatus = FulfillmentStatus.PENDING
    customer_approval_status: CustomerApprovalStatus = CustomerApprovalStatus.NOT_REQUIRED
    customer_approval_expires_at: str | None = None
    currency_code: str = "MXN"
    delivery_fee: Decimal = Decimal("0")
    totals: OrderTotals = field(default_factory=OrderTotals.zero)
    external_order_reference: str | None = None
    sale_id: str | None = None
    quote_id: str | None = None
    whatsapp_order_id: str | None = None
    operation_id: str | None = None
    created_by_user_id: str | None = None
    confirmed_by_user_id: str | None = None
    cancelled_by_user_id: str | None = None
    lines: list[CustomerOrderLine] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, branch_id: str, channel: OrderChannel, order_type: OrderType,
        fulfillment_type: FulfillmentType, customer_id: str | None = None,
        contact_name: str | None = None, contact_phone: str | None = None,
        created_by_user_id: str | None = None,
        external_order_reference: str | None = None,
        whatsapp_order_id: str | None = None,
        operation_id: str | None = None,
    ) -> "CustomerOrder":
        _ids(branch_id)
        for value in (customer_id, created_by_user_id):
            if value is not None:
                _ids(value)
        return cls(
            id=new_uuid(), branch_id=branch_id, channel=channel, order_type=order_type,
            fulfillment_type=fulfillment_type, customer_id=customer_id,
            contact_name=contact_name, contact_phone=contact_phone,
            created_by_user_id=created_by_user_id,
            external_order_reference=external_order_reference,
            whatsapp_order_id=whatsapp_order_id,
            operation_id=operation_id,
        )

    def _find_line(self, line_id: str) -> CustomerOrderLine:
        for line in self.lines:
            if line.id == line_id:
                return line
        raise OrderLineNotFoundError(f"No existe la línea {line_id} en el pedido {self.id}")

    def add_line(self, line: CustomerOrderLine) -> None:
        if not OrderLifecyclePolicy.is_line_mutable(self.status):
            raise InvalidOrderStateError(
                f"No se pueden agregar líneas a un pedido en estado {self.status.value}")
        if line.order_id != self.id:
            raise OrderNotFoundError("La línea no pertenece a este pedido")
        self.lines.append(line)
        self._recalculate_totals()
        self.updated_at = _now()

    def remove_line(self, line_id: str) -> None:
        if not OrderLifecyclePolicy.is_line_mutable(self.status):
            raise InvalidOrderStateError(
                f"No se pueden eliminar líneas de un pedido en estado {self.status.value}")
        line = self._find_line(line_id)
        self.lines.remove(line)
        self._recalculate_totals()
        self.updated_at = _now()

    def _recalculate_totals(self) -> None:
        self.totals = OrderTotalsService.calculate(self.lines, delivery_fee=self.delivery_fee)

    def confirm(self, *, confirmed_by_user_id: str) -> None:
        _ids(confirmed_by_user_id)
        OrderConfirmationPolicy.ensure_can_confirm(
            status=self.status, line_count=len(self.lines), total=self.totals.grand_total)
        self.status = OrderStatus.CONFIRMED
        self.confirmed_by_user_id = confirmed_by_user_id
        self.updated_at = _now()

    def mark_reserved(self) -> None:
        """§23: every line reserved. Does not itself talk to Inventory —
        the use case orchestrating the reservation calls this once all line
        reservations succeeded. Also advances `OrderStatus` CONFIRMED ->
        IN_FULFILLMENT — a reserved order is, by definition, actively being
        fulfilled (§14); nothing else in this domain triggered that
        transition before ORD-14 found the gap."""
        OrderReservationRequiredPolicy.ensure_confirmed(self.status)
        if self.status == OrderStatus.CONFIRMED:
            self.move_to_fulfillment()
        self.fulfillment_status = FulfillmentStatus.RESERVED
        self.updated_at = _now()

    def mark_reservation_failed(self) -> None:
        self.fulfillment_status = FulfillmentStatus.FAILED
        self.updated_at = _now()

    def assign_preparation(self, *, assigned_to_user_id: str, station_id: str | None = None) -> None:
        OrderPreparationPolicy.ensure_reserved_before_preparation(self.fulfillment_status)
        OrderPreparationPolicy.ensure_transition(
            current=self.preparation_status, target=PreparationStatus.ASSIGNED)
        _ids(assigned_to_user_id)
        self.assigned_to_user_id = assigned_to_user_id
        self.station_id = station_id
        self.preparation_status = PreparationStatus.ASSIGNED
        self.updated_at = _now()

    def start_preparation(self) -> None:
        OrderPreparationPolicy.ensure_transition(
            current=self.preparation_status, target=PreparationStatus.IN_PROGRESS)
        self.preparation_status = PreparationStatus.IN_PROGRESS
        self.preparation_started_at = _now()
        self.fulfillment_status = FulfillmentStatus.PREPARING
        self.updated_at = _now()

    def complete_preparation(self) -> None:
        """§25: only reachable once every line has left `PENDING`/`RESERVED`
        for a prepared/terminal state — a half-prepared order cannot be
        marked ready."""
        unfinished = [
            line for line in self.lines
            if line.status not in (
                OrderLineStatus.PREPARED, OrderLineStatus.READY,
                OrderLineStatus.SUBSTITUTED, OrderLineStatus.REJECTED,
            )
        ]
        if unfinished:
            raise OrderPreparationNotAllowedError(
                f"{len(unfinished)} línea(s) sin preparar")
        OrderPreparationPolicy.ensure_transition(
            current=self.preparation_status, target=PreparationStatus.READY)
        self.preparation_status = PreparationStatus.READY
        self.preparation_completed_at = _now()
        self.fulfillment_status = FulfillmentStatus.READY
        self.updated_at = _now()

    def cancel_preparation(self) -> None:
        OrderPreparationPolicy.ensure_transition(
            current=self.preparation_status, target=PreparationStatus.CANCELLED)
        self.preparation_status = PreparationStatus.CANCELLED
        self.updated_at = _now()

    def mark_ready_for_pickup(self, *, verification_code: str) -> None:
        """§30: assigns the code the customer must present at the counter.
        Only meaningful for COUNTER/PICKUP orders that already finished
        preparation (ORD-9's `complete_preparation()`)."""
        PickupPolicy.ensure_is_pickup_order(self.fulfillment_type)
        PickupPolicy.ensure_ready(self.fulfillment_status)
        self.pickup_verification_code = verification_code
        self.updated_at = _now()

    def complete_pickup(self, *, presented_code: str) -> None:
        """§30: validates identity (code) and payment before completing the
        hand-over — reuses `complete()`'s own COMPLETED/DELIVERED
        transition rather than duplicating it."""
        PickupPolicy.ensure_is_pickup_order(self.fulfillment_type)
        PickupPolicy.ensure_verification_matches(
            expected_code=self.pickup_verification_code, presented_code=presented_code)
        PickupPolicy.ensure_paid(self.payment_status)
        self.complete()

    def mark_dispatched(self) -> None:
        """§36: the order's own view of dispatch — the `DeliveryJob`
        aggregate (ORD-15) tracks the actual dispatch event; this only
        updates the order's `FulfillmentStatus` so order-level queries never
        need to join across bounded contexts to know "is this out for
        delivery"."""
        self.fulfillment_status = FulfillmentStatus.DISPATCHED
        self.updated_at = _now()

    def complete_delivery(self) -> None:
        """§38: completes a home-delivery order once the `DeliveryJob`
        reports a successful attempt. Payment validation is deliberately
        NOT done here — cash-on-delivery collection is ORD-20's own concern,
        and by the time an attempt succeeds the money question is already
        resolved one way or another."""
        if self.fulfillment_status != FulfillmentStatus.DISPATCHED:
            raise InvalidOrderStateError(
                f"El pedido no está despachado (estado: {self.fulfillment_status.value})")
        self.complete()

    def apply_weight_evaluation(self, *, line_id: str, evaluation: WeightAdjustmentEvaluation,
                                 approval_expires_at: str | None = None) -> None:
        """§26-27: applies a `CatchWeightAdjustmentPolicy` outcome to one
        line, re-derives totals from it, and — only when the adjustment
        exceeds tolerance — puts the WHOLE order into
        `CustomerApprovalStatus.PENDING` (dispatch must wait for every
        pending line to resolve, not just this one). `approval_expires_at`
        (§72's future configurable timeout) is only recorded when the
        adjustment actually needs approval."""
        line = self._find_line(line_id)
        line.apply_weight_evaluation(evaluation)
        if not evaluation.within_tolerance:
            self.customer_approval_status = CustomerApprovalStatus.PENDING
            self.customer_approval_expires_at = approval_expires_at
        self._recalculate_totals()
        self.updated_at = _now()

    def accept_customer_adjustment(self, line_id: str) -> None:
        self._ensure_approval_not_expired()
        line = self._find_line(line_id)
        line.accept_customer_adjustment()
        self._sync_customer_approval_status()
        self._recalculate_totals()
        self.updated_at = _now()

    def reject_customer_adjustment(self, line_id: str) -> None:
        self._ensure_approval_not_expired()
        line = self._find_line(line_id)
        line.reject_customer_adjustment()
        self._sync_customer_approval_status()
        self._recalculate_totals()
        self.updated_at = _now()

    def propose_substitution(
        self, *, line_id: str, substitute_product_id: str, substitution_type: SubstitutionType,
        new_unit_price: Decimal, reason: str, approval_expires_at: str | None = None,
    ) -> None:
        line = self._find_line(line_id)
        line.propose_substitution(
            substitute_product_id=substitute_product_id, substitution_type=substitution_type,
            new_unit_price=new_unit_price, reason=reason)
        self.customer_approval_status = CustomerApprovalStatus.PENDING
        self.customer_approval_expires_at = approval_expires_at
        self.updated_at = _now()

    def accept_substitution(self, line_id: str) -> None:
        self._ensure_approval_not_expired()
        line = self._find_line(line_id)
        line.accept_substitution()
        self._sync_customer_approval_status()
        self._recalculate_totals()
        self.updated_at = _now()

    def reject_substitution(self, line_id: str) -> None:
        self._ensure_approval_not_expired()
        line = self._find_line(line_id)
        line.reject_substitution()
        self._sync_customer_approval_status()
        self._recalculate_totals()
        self.updated_at = _now()

    def _ensure_approval_not_expired(self) -> None:
        if self.customer_approval_status == CustomerApprovalStatus.EXPIRED:
            raise CustomerApprovalExpiredError(
                "La ventana de aprobación del cliente ya expiró")

    def expire_customer_approval(self, *, now: datetime) -> None:
        """§27/ORD-11: no customer response within the configured window is
        treated as an implicit rejection of every still-pending line — never
        left dangling in `PENDING_CUSTOMER_APPROVAL` forever."""
        if self.customer_approval_status != CustomerApprovalStatus.PENDING:
            raise InvalidOrderStateError(
                f"No hay aprobación pendiente que expirar (estado: "
                f"{self.customer_approval_status.value})")
        if not self.customer_approval_expires_at:
            raise InvalidOrderStateError("La aprobación pendiente no tiene fecha límite")
        if datetime.fromisoformat(self.customer_approval_expires_at) > now:
            raise ApprovalExpirationNotDueError(
                f"La ventana vence hasta {self.customer_approval_expires_at}, todavía no corresponde")
        for line in self.lines:
            if line.status == OrderLineStatus.PENDING_CUSTOMER_APPROVAL:
                line.mark_status(OrderLineStatus.REJECTED)
        self.customer_approval_status = CustomerApprovalStatus.EXPIRED
        self._recalculate_totals()
        self.updated_at = _now()

    def _sync_customer_approval_status(self) -> None:
        if any(line.status == OrderLineStatus.PENDING_CUSTOMER_APPROVAL for line in self.lines):
            self.customer_approval_status = CustomerApprovalStatus.PENDING
        elif any(line.status == OrderLineStatus.REJECTED for line in self.lines):
            self.customer_approval_status = CustomerApprovalStatus.REJECTED
        else:
            self.customer_approval_status = CustomerApprovalStatus.ACCEPTED

    def move_to_fulfillment(self) -> None:
        OrderLifecyclePolicy.ensure_transition(
            current=self.status, target=OrderStatus.IN_FULFILLMENT)
        self.status = OrderStatus.IN_FULFILLMENT
        self.updated_at = _now()

    def complete(self) -> None:
        OrderLifecyclePolicy.ensure_transition(current=self.status, target=OrderStatus.COMPLETED)
        self.status = OrderStatus.COMPLETED
        self.fulfillment_status = FulfillmentStatus.DELIVERED
        self.updated_at = _now()

    def cancel(self, *, cancelled_by_user_id: str, reason: str) -> None:
        _ids(cancelled_by_user_id)
        OrderCancellationPolicy.ensure_can_cancel(status=self.status, reason=reason)
        self.status = OrderStatus.CANCELLED
        self.cancelled_by_user_id = cancelled_by_user_id
        self.updated_at = _now()

    def set_delivery_address(self, address_id: str) -> None:
        _ids(address_id)
        self.delivery_address_id = address_id
        self.updated_at = _now()

    def set_delivery_fee(self, delivery_fee: Decimal) -> None:
        """§22: Delivery's fee is data-driven (`DeliveryFeePolicy`), never a
        product-price change — this only ever touches `delivery_fee`/
        `totals`, never a line's `unit_price_snapshot`."""
        self.delivery_fee = money(delivery_fee)
        self._recalculate_totals()
        self.updated_at = _now()

    def schedule(self, *, scheduled_for: str, window_start: str, window_end: str,
                 activation_at: str) -> None:
        """§19: attach/replace this order's delivery schedule. Only valid
        while the order itself hasn't left the mutable draft/confirmation
        stage — a schedule is part of the commitment being captured, not a
        change bolted onto an already-fulfilling order (that's
        `reschedule()`'s job once `ScheduleStatus` allows it)."""
        ScheduledOrderPolicy.ensure_valid_window(window_start=window_start, window_end=window_end)
        self.scheduled_for = scheduled_for
        self.delivery_window_start = window_start
        self.delivery_window_end = window_end
        self.activation_at = activation_at
        self.schedule_status = ScheduleStatus.SCHEDULED
        self.updated_at = _now()

    def reschedule(self, *, scheduled_for: str, window_start: str, window_end: str,
                    activation_at: str) -> None:
        ScheduledOrderPolicy.ensure_can_reschedule(self.schedule_status)
        ScheduledOrderPolicy.ensure_valid_window(window_start=window_start, window_end=window_end)
        self.scheduled_for = scheduled_for
        self.delivery_window_start = window_start
        self.delivery_window_end = window_end
        self.activation_at = activation_at
        self.schedule_status = ScheduleStatus.RESCHEDULED
        self.updated_at = _now()

    def activate_schedule(self, *, now: datetime) -> None:
        """§19: activation moves a SCHEDULED order into normal fulfillment
        (does NOT itself check inventory/capacity/route — that cross-context
        evaluation belongs to the use case calling this, ORD-8+)."""
        ScheduledOrderPolicy.ensure_can_activate(
            status=self.schedule_status, activation_at=self.activation_at, now=now)
        self.schedule_status = ScheduleStatus.ACTIVATED
        self.updated_at = _now()

    def cancel_schedule(self) -> None:
        ScheduledOrderPolicy.ensure_can_cancel(self.schedule_status)
        self.schedule_status = ScheduleStatus.CANCELLED
        self.updated_at = _now()

    def close(self) -> None:
        OrderLifecyclePolicy.ensure_transition(current=self.status, target=OrderStatus.CLOSED)
        self.status = OrderStatus.CLOSED
        self.updated_at = _now()

    def reverse(self) -> None:
        OrderLifecyclePolicy.ensure_transition(current=self.status, target=OrderStatus.REVERSED)
        self.status = OrderStatus.REVERSED
        self.updated_at = _now()

    def link_sale(self, sale_id: str) -> None:
        """§22: projects this order onto a commercial `Sale`. Idempotent for
        the SAME sale (a retried projection call is a no-op) but never
        silently repoints an order already linked to a DIFFERENT sale."""
        if self.sale_id == sale_id:
            return
        if self.sale_id is not None:
            raise OrderAlreadyLinkedToSaleError(
                f"El pedido ya está vinculado a la venta {self.sale_id}")
        _ids(sale_id)
        self.sale_id = sale_id
        self.updated_at = _now()

    def apply_payment_status(self, status: PaymentStatus) -> None:
        """§15/§22: projects the Sale's real payment state onto this order.
        Orders/Delivery never computes payment math itself — the caller
        (an application-layer use case) derives `status` from the linked
        Sale via `OrderPaymentPolicy.resolve_from_amounts()` or an explicit
        method-specific state (credit approved, cash-on-delivery, refund)."""
        OrderPaymentPolicy.ensure_transition(current=self.payment_status, target=status)
        self.payment_status = status
        self.updated_at = _now()
