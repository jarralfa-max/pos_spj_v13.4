"""OrderResult — the return type every Pedidos/Delivery use case produces.
Mirrors backend/application/sales/result.py's `SaleResult` shape exactly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain.orders_delivery.exceptions import (
    ApprovalExpirationNotDueError,
    AssignmentNotFoundError,
    CashCollectionNotFoundError,
    DriverProfileNotFoundError,
    CustomerApprovalExpiredError,
    CustomerApprovalRequiredError,
    DeliveryAddressRequiredError,
    DeliveryDriverRequiredError,
    DeliveryEvidenceRequiredError,
    DeliveryFailureReasonRequiredError,
    DeliveryJobNotFoundError,
    DeliveryZoneNotAvailableError,
    DispatchNotAllowedError,
    DriverNotAvailableError,
    InvalidAddressError,
    InvalidAssignmentStateError,
    InvalidCashCollectionError,
    InvalidDeliveryJobStateError,
    InvalidRedeliveryStateError,
    InvalidRouteStateError,
    InvalidRouteStopError,
    InvalidPackageError,
    InvalidPaymentStatusError,
    InvalidSettlementStateError,
    OrderAlreadyLinkedToSaleError,
    OrderNotLinkedToSaleError,
    RedeliveryNotAllowedError,
    RedeliveryRequestNotFoundError,
    RefundNotAllowedError,
    SaleProjectionFailedError,
    SettlementNotFoundError,
    SettlementRequiresCollectionsError,
    PaymentRequiredForPickupError,
    PickupVerificationFailedError,
    InvalidOrderMoneyError,
    InvalidOrderQuantityError,
    InvalidOrderScheduleError,
    InvalidOrdersDeliveryAuditFieldError,
    InvalidOrderStateError,
    OrderActivationNotDueError,
    OrderCancellationNotAllowedError,
    OrderConfirmationRequiredError,
    OrderEmptyError,
    OrderLineNotFoundError,
    OrderInventoryReservationFailedError,
    OrderNotFoundError,
    OrderPreparationNotAllowedError,
    RouteNotFoundError,
    OrdersDeliveryConfigurationError,
    OrdersDeliveryDomainError,
    OrdersDeliveryPermissionDeniedError,
    OrdersDeliverySegregationOfDutiesError,
    DuplicateOperationError,
    SubstitutionNotAllowedError,
)


@dataclass(frozen=True, slots=True)
class OrderResult:
    success: bool
    message: str = ""
    operation_id: str | None = None
    entity_id: str | None = None
    error_code: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", *, entity_id: str | None = None,
           operation_id: str | None = None, **data: Any) -> "OrderResult":
        return cls(True, message, operation_id, entity_id, None, dict(data))

    @classmethod
    def fail(cls, message: str, error_code: str, *,
             operation_id: str | None = None, **data: Any) -> "OrderResult":
        return cls(False, message, operation_id, None, error_code, dict(data))


_ERROR_CODES: tuple[tuple[type[OrdersDeliveryDomainError], str], ...] = (
    (OrdersDeliveryPermissionDeniedError, "PERMISSION_DENIED"),
    (OrdersDeliveryConfigurationError, "CONFIGURATION_ERROR"),
    (OrdersDeliverySegregationOfDutiesError, "SEGREGATION_OF_DUTIES"),
    (InvalidOrdersDeliveryAuditFieldError, "INVALID_AUDIT_FIELD"),
    (OrderNotFoundError, "NOT_FOUND"),
    (OrderLineNotFoundError, "LINE_NOT_FOUND"),
    (InvalidOrderStateError, "INVALID_STATE"),
    (OrderConfirmationRequiredError, "CONFIRMATION_REQUIRED"),
    (OrderEmptyError, "EMPTY_ORDER"),
    (OrderCancellationNotAllowedError, "CANCELLATION_NOT_ALLOWED"),
    (InvalidOrderQuantityError, "INVALID_QUANTITY"),
    (InvalidOrderMoneyError, "INVALID_MONEY"),
    (DuplicateOperationError, "DUPLICATE_OPERATION"),
    (OrderActivationNotDueError, "ACTIVATION_NOT_DUE"),
    (InvalidOrderScheduleError, "INVALID_SCHEDULE"),
    (InvalidAddressError, "INVALID_ADDRESS"),
    (DeliveryAddressRequiredError, "DELIVERY_ADDRESS_REQUIRED"),
    (DeliveryZoneNotAvailableError, "DELIVERY_ZONE_NOT_AVAILABLE"),
    (OrderInventoryReservationFailedError, "INVENTORY_RESERVATION_FAILED"),
    (OrderPreparationNotAllowedError, "PREPARATION_NOT_ALLOWED"),
    (CustomerApprovalRequiredError, "CUSTOMER_APPROVAL_REQUIRED"),
    (CustomerApprovalExpiredError, "CUSTOMER_APPROVAL_EXPIRED"),
    (ApprovalExpirationNotDueError, "APPROVAL_EXPIRATION_NOT_DUE"),
    (SubstitutionNotAllowedError, "SUBSTITUTION_NOT_ALLOWED"),
    (InvalidPackageError, "INVALID_PACKAGE"),
    (PickupVerificationFailedError, "PICKUP_VERIFICATION_FAILED"),
    (PaymentRequiredForPickupError, "PAYMENT_REQUIRED"),
    (DeliveryJobNotFoundError, "DELIVERY_JOB_NOT_FOUND"),
    (InvalidDeliveryJobStateError, "INVALID_DELIVERY_STATE"),
    (DeliveryDriverRequiredError, "DELIVERY_DRIVER_REQUIRED"),
    (DriverNotAvailableError, "DRIVER_NOT_AVAILABLE"),
    (InvalidAssignmentStateError, "INVALID_ASSIGNMENT_STATE"),
    (AssignmentNotFoundError, "ASSIGNMENT_NOT_FOUND"),
    (DriverProfileNotFoundError, "DRIVER_PROFILE_NOT_FOUND"),
    (RouteNotFoundError, "ROUTE_NOT_FOUND"),
    (InvalidRouteStateError, "INVALID_ROUTE_STATE"),
    (InvalidRouteStopError, "INVALID_ROUTE_STOP"),
    (DispatchNotAllowedError, "DISPATCH_NOT_ALLOWED"),
    (DeliveryEvidenceRequiredError, "DELIVERY_EVIDENCE_REQUIRED"),
    (DeliveryFailureReasonRequiredError, "DELIVERY_FAILURE_REASON_REQUIRED"),
    (InvalidRedeliveryStateError, "INVALID_REDELIVERY_STATE"),
    (RedeliveryNotAllowedError, "REDELIVERY_NOT_ALLOWED"),
    (RedeliveryRequestNotFoundError, "REDELIVERY_REQUEST_NOT_FOUND"),
    (InvalidCashCollectionError, "INVALID_CASH_COLLECTION"),
    (CashCollectionNotFoundError, "CASH_COLLECTION_NOT_FOUND"),
    (InvalidSettlementStateError, "INVALID_SETTLEMENT_STATE"),
    (SettlementRequiresCollectionsError, "SETTLEMENT_REQUIRES_COLLECTIONS"),
    (SettlementNotFoundError, "SETTLEMENT_NOT_FOUND"),
    (SaleProjectionFailedError, "SALE_PROJECTION_FAILED"),
    (OrderAlreadyLinkedToSaleError, "ORDER_ALREADY_LINKED_TO_SALE"),
    (OrderNotLinkedToSaleError, "ORDER_NOT_LINKED_TO_SALE"),
    (InvalidPaymentStatusError, "INVALID_PAYMENT_STATUS"),
    (RefundNotAllowedError, "REFUND_NOT_ALLOWED"),
)


def fail_from_domain_error(exc: OrdersDeliveryDomainError, *,
                            operation_id: str | None = None) -> OrderResult:
    """Translate any typed Pedidos/Delivery domain exception into an
    `OrderResult.fail()` — one mapping table instead of a bespoke
    try/except per use case."""
    code = next((code for cls, code in _ERROR_CODES if isinstance(exc, cls)), "VALIDATION")
    return OrderResult.fail(str(exc), code, operation_id=operation_id)
