from decimal import Decimal

import pytest

from backend.domain.payments.entities import PaymentIntent
from backend.domain.payments.enums import (
    PaymentChannel, PaymentIntentStatus, PaymentMethod, PaymentPurpose,
)
from backend.domain.payments.exceptions import (
    PaymentConfirmationMismatchError, PaymentIntentTransitionError,
)


def make_intent(**overrides):
    values = dict(
        aggregate_type="SALE", aggregate_id="sale-123",
        channel=PaymentChannel.POS, method=PaymentMethod.QR,
        purpose=PaymentPurpose.FULL, amount=Decimal("125.50"),
    )
    values.update(overrides)
    return PaymentIntent.create(**values)


def test_intent_uses_opaque_uuidv7_external_reference():
    intent = make_intent()
    assert intent.external_reference == intent.id
    assert len(intent.id) == 36
    assert "sale-123" not in intent.external_reference


def test_approval_requires_matching_reference_amount_and_currency():
    intent = make_intent()
    intent.mark_pending()
    with pytest.raises(PaymentConfirmationMismatchError):
        intent.approve(
            provider_payment_id="mp-123", amount=Decimal("125.50"),
            currency="MXN", external_reference="another-intent",
        )
    with pytest.raises(PaymentConfirmationMismatchError):
        intent.approve(
            provider_payment_id="mp-123", amount=Decimal("125.49"),
            currency="MXN", external_reference=intent.id,
        )
    with pytest.raises(PaymentConfirmationMismatchError):
        intent.approve(
            provider_payment_id="mp-123", amount=Decimal("125.50"),
            currency="USD", external_reference=intent.id,
        )


def test_exact_provider_confirmation_is_idempotent():
    intent = make_intent()
    intent.mark_pending()
    intent.approve(
        provider_payment_id="mp-123", amount=Decimal("125.50"),
        currency="MXN", external_reference=intent.id,
    )
    intent.approve(
        provider_payment_id="mp-123", amount=Decimal("125.50"),
        currency="MXN", external_reference=intent.id,
    )
    assert intent.status is PaymentIntentStatus.APPROVED
    assert intent.provider_payment_id == "mp-123"


def test_a_different_payment_cannot_reapprove_an_approved_intent():
    intent = make_intent()
    intent.mark_pending()
    intent.approve(
        provider_payment_id="mp-123", amount=Decimal("125.50"),
        currency="MXN", external_reference=intent.id,
    )
    with pytest.raises(PaymentIntentTransitionError):
        intent.approve(
            provider_payment_id="mp-456", amount=Decimal("125.50"),
            currency="MXN", external_reference=intent.id,
        )


def test_terminal_intent_cannot_be_approved():
    intent = make_intent()
    intent.cancel()
    with pytest.raises(PaymentIntentTransitionError):
        intent.approve(
            provider_payment_id="mp-123", amount=Decimal("125.50"),
            currency="MXN", external_reference=intent.id,
        )


def test_whatsapp_intent_supports_deposit_purpose():
    intent = make_intent(
        aggregate_type="WHATSAPP_ORDER", aggregate_id="wa-order-2026-42",
        channel=PaymentChannel.WHATSAPP, method=PaymentMethod.CHECKOUT,
        purpose=PaymentPurpose.DEPOSIT, amount=Decimal("50.00"),
    )
    assert intent.purpose is PaymentPurpose.DEPOSIT
    assert intent.channel is PaymentChannel.WHATSAPP


def test_money_must_be_decimal_and_positive():
    with pytest.raises(ValueError):
        make_intent(amount=125.50)
    with pytest.raises(ValueError):
        make_intent(amount=Decimal("0"))
