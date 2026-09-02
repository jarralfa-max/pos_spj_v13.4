"""DriverCashCollection (master prompt §44-45) — what a driver actually
collected against a `DeliveryJob.cash_to_collect`. Settlement/reconciliation
across many collections is ORD-21's own aggregate (`DriverSettlement`); this
entity only records ONE delivery's collection outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.orders_delivery.enums import CollectionPaymentMethod, CollectionStatus
from backend.domain.orders_delivery.exceptions import InvalidCashCollectionError
from backend.domain.orders_delivery.value_objects.order_money import money


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DriverCashCollection:
    id: str
    delivery_job_id: str
    driver_id: str
    expected_amount: Decimal
    payment_method: CollectionPaymentMethod
    collected_amount: Decimal = Decimal("0")
    reference: str | None = None
    status: CollectionStatus = CollectionStatus.EXPECTED
    collected_at: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, delivery_job_id: str, driver_id: str, expected_amount: Decimal,
        payment_method: CollectionPaymentMethod,
    ) -> "DriverCashCollection":
        validate_uuidv7(delivery_job_id)
        validate_uuidv7(driver_id)
        return cls(
            id=new_uuid(), delivery_job_id=delivery_job_id, driver_id=driver_id,
            expected_amount=money(expected_amount), payment_method=payment_method,
        )

    def record_collection(self, *, collected_amount: Decimal, reference: str | None = None) -> None:
        if self.status not in (CollectionStatus.EXPECTED, CollectionStatus.FAILED):
            raise InvalidCashCollectionError(
                f"No se puede registrar un cobro en estado {self.status.value}")
        collected_amount = money(collected_amount)
        if collected_amount <= 0:
            self.status = CollectionStatus.FAILED
        elif collected_amount < self.expected_amount:
            self.status = CollectionStatus.PARTIALLY_COLLECTED
        else:
            self.status = CollectionStatus.COLLECTED
        self.collected_amount = collected_amount
        self.reference = reference
        self.collected_at = _now()
        self.updated_at = _now()

    def dispute(self) -> None:
        if self.status not in (CollectionStatus.COLLECTED, CollectionStatus.PARTIALLY_COLLECTED):
            raise InvalidCashCollectionError(
                f"No se puede disputar un cobro en estado {self.status.value}")
        self.status = CollectionStatus.DISPUTED
        self.updated_at = _now()

    def mark_pending_settlement(self) -> None:
        if self.status not in (CollectionStatus.COLLECTED, CollectionStatus.PARTIALLY_COLLECTED):
            raise InvalidCashCollectionError(
                f"No se puede enviar a liquidación un cobro en estado {self.status.value}")
        self.status = CollectionStatus.PENDING_SETTLEMENT
        self.updated_at = _now()

    def mark_settled(self) -> None:
        if self.status != CollectionStatus.PENDING_SETTLEMENT:
            raise InvalidCashCollectionError(
                f"No se puede liquidar un cobro en estado {self.status.value}")
        self.status = CollectionStatus.SETTLED
        self.updated_at = _now()
