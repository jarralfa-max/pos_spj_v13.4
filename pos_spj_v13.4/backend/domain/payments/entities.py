"""PaymentIntent — provider-independent intent to collect money.

An intent belongs to one ERP aggregate and one channel. Its UUIDv7 is also
the opaque external_reference sent to the provider; customer phone numbers,
sale folios and other personal/business identifiers are never provider refs.
Only an authoritative provider lookup may approve an intent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.payments.enums import (
    PaymentChannel,
    PaymentIntentStatus,
    PaymentMethod,
    PaymentPurpose,
)
from backend.domain.payments.exceptions import (
    PaymentConfirmationMismatchError,
    PaymentIntentTransitionError,
)
from backend.domain.sales.value_objects.money import money
from backend.shared.ids import new_uuid

_CURRENCY = re.compile(r"^[A-Z]{3}$")
_PROVIDER_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class PaymentIntent:
    id: str
    aggregate_type: str
    aggregate_id: str
    channel: PaymentChannel
    method: PaymentMethod
    purpose: PaymentPurpose
    amount: Decimal
    currency: str = "MXN"
    status: PaymentIntentStatus = PaymentIntentStatus.CREATED
    idempotency_key: str = field(default_factory=new_uuid)
    provider_preference_id: str | None = None
    provider_order_id: str | None = None
    checkout_url: str | None = None
    provider_payment_id: str | None = None
    expires_at: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, aggregate_type: str, aggregate_id: str,
        channel: PaymentChannel, method: PaymentMethod,
        purpose: PaymentPurpose, amount: Decimal, currency: str = "MXN",
        expires_at: str | None = None,
    ) -> "PaymentIntent":
        aggregate_type = str(aggregate_type or "").strip().upper()
        aggregate_id = str(aggregate_id or "").strip()
        currency = str(currency or "").strip().upper()
        if aggregate_type not in {"SALE", "WHATSAPP_ORDER"}:
            raise ValueError("aggregate_type must be SALE or WHATSAPP_ORDER")
        if not aggregate_id:
            raise ValueError("aggregate_id is required")
        if not _CURRENCY.fullmatch(currency):
            raise ValueError("currency must be a 3-letter ISO currency code")
        return cls(
            id=new_uuid(), aggregate_type=aggregate_type, aggregate_id=aggregate_id,
            channel=PaymentChannel(channel), method=PaymentMethod(method),
            purpose=PaymentPurpose(purpose), amount=money(amount, allow_zero=False),
            currency=currency, expires_at=expires_at,
        )

    @property
    def external_reference(self) -> str:
        """Opaque, immutable provider reference; never a phone or sale folio."""
        return self.id

    def mark_pending(
        self, *, provider_preference_id: str | None = None,
        provider_order_id: str | None = None, checkout_url: str | None = None,
    ) -> None:
        if self.status not in {PaymentIntentStatus.CREATED, PaymentIntentStatus.PENDING}:
            raise PaymentIntentTransitionError(
                f"Cannot start provider collection from {self.status.value}")
        if provider_preference_id is not None and not _PROVIDER_ID.fullmatch(provider_preference_id):
            raise ValueError("Invalid provider_preference_id")
        if provider_order_id is not None and not _PROVIDER_ID.fullmatch(provider_order_id):
            raise ValueError("Invalid provider_order_id")
        self.provider_preference_id = provider_preference_id or self.provider_preference_id
        self.provider_order_id = provider_order_id or self.provider_order_id
        self.checkout_url = checkout_url or self.checkout_url
        self.status = PaymentIntentStatus.PENDING
        self.updated_at = _now()

    def approve(
        self, *, provider_payment_id: str, amount: Decimal,
        currency: str, external_reference: str,
    ) -> None:
        """Approve only after the adapter has fetched the payment from MP."""
        if self.status is PaymentIntentStatus.APPROVED:
            if self.provider_payment_id == provider_payment_id:
                return  # exact replay is harmless
            raise PaymentIntentTransitionError("Intent is already approved by another payment")
        if self.status not in {PaymentIntentStatus.CREATED, PaymentIntentStatus.PENDING}:
            raise PaymentIntentTransitionError(
                f"Cannot approve an intent in {self.status.value}")
        if not _PROVIDER_ID.fullmatch(str(provider_payment_id or "")):
            raise PaymentConfirmationMismatchError("Provider payment id is invalid")
        if external_reference != self.external_reference:
            raise PaymentConfirmationMismatchError("Provider reference does not match intent")
        if str(currency or "").strip().upper() != self.currency:
            raise PaymentConfirmationMismatchError("Provider currency does not match intent")
        try:
            confirmed_amount = money(amount, allow_zero=False)
        except (TypeError, ValueError) as exc:
            raise PaymentConfirmationMismatchError("Provider amount is invalid") from exc
        if confirmed_amount != self.amount:
            raise PaymentConfirmationMismatchError("Provider amount does not match intent")
        self.provider_payment_id = str(provider_payment_id)
        self.status = PaymentIntentStatus.APPROVED
        self.updated_at = _now()

    def reject(self) -> None:
        self._transition_terminal(PaymentIntentStatus.REJECTED)

    def cancel(self) -> None:
        self._transition_terminal(PaymentIntentStatus.CANCELLED)

    def expire(self) -> None:
        self._transition_terminal(PaymentIntentStatus.EXPIRED)

    def _transition_terminal(self, target: PaymentIntentStatus) -> None:
        if self.status not in {PaymentIntentStatus.CREATED, PaymentIntentStatus.PENDING}:
            raise PaymentIntentTransitionError(
                f"Cannot transition {self.status.value} to {target.value}")
        self.status = target
        self.updated_at = _now()
