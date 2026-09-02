"""LOY-13 — VoucherDefinition / VoucherInstance / VoucherTransaction /
VoucherRedemption / VoucherBalancePolicy (master prompt §22)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.commercial_instruments.entities.voucher_definition import VoucherDefinition
from backend.domain.commercial_instruments.entities.voucher_instance import VoucherInstance
from backend.domain.commercial_instruments.entities.voucher_redemption import VoucherRedemption
from backend.domain.commercial_instruments.entities.voucher_transaction import VoucherTransaction
from backend.domain.commercial_instruments.enums import VoucherInstanceStatus, VoucherType
from backend.domain.commercial_instruments.exceptions import (
    InvalidVoucherDefinitionError,
    InvalidVoucherInstanceStateError,
    InvalidVoucherTransactionAmountError,
    InvalidVoucherTransactionStateError,
)
from backend.domain.commercial_instruments.policies.voucher_balance_policy import (
    VoucherBalancePolicy,
)
from backend.shared.ids import new_uuid


class TestVoucherDefinition:
    def test_create_defaults(self):
        definition = VoucherDefinition.create("REFUND", "Vale de devolución",
                                               VoucherType.REFUND_VOUCHER)
        assert definition.active is True

    def test_requires_code_and_name(self):
        with pytest.raises(InvalidVoucherDefinitionError):
            VoucherDefinition.create("", "X", VoucherType.STORE_CREDIT)


class TestVoucherInstance:
    def test_issue_defaults_to_active(self):
        instance = VoucherInstance.issue(new_uuid(), "VAL-001")
        assert instance.status is VoucherInstanceStatus.ACTIVE
        assert instance.is_usable() is True

    def test_reserve_release_flow(self):
        instance = VoucherInstance.issue(new_uuid(), "VAL-001")
        instance.reserve(new_uuid())
        assert instance.status is VoucherInstanceStatus.RESERVED
        instance.release(restore_status=VoucherInstanceStatus.ACTIVE)
        assert instance.status is VoucherInstanceStatus.ACTIVE

    def test_mark_redeemed_fully_vs_partially(self):
        instance = VoucherInstance.issue(new_uuid(), "VAL-001")
        instance.reserve(new_uuid())
        instance.mark_redeemed(fully=False)
        assert instance.status is VoucherInstanceStatus.PARTIALLY_REDEEMED

        instance.reserve(new_uuid())
        instance.mark_redeemed(fully=True)
        assert instance.status is VoucherInstanceStatus.REDEEMED

    def test_cannot_reserve_a_redeemed_voucher(self):
        instance = VoucherInstance.issue(new_uuid(), "VAL-001")
        instance.reserve(new_uuid())
        instance.mark_redeemed(fully=True)
        with pytest.raises(InvalidVoucherInstanceStateError):
            instance.reserve(new_uuid())

    def test_partially_redeemed_can_be_reserved_again(self):
        instance = VoucherInstance.issue(new_uuid(), "VAL-001")
        instance.reserve(new_uuid())
        instance.mark_redeemed(fully=False)
        instance.reserve(new_uuid())
        assert instance.status is VoucherInstanceStatus.RESERVED

    def test_cancel_block_reverse_require_reason(self):
        for method in ("cancel", "block", "reverse"):
            instance = VoucherInstance.issue(new_uuid(), "VAL-001")
            with pytest.raises(InvalidVoucherInstanceStateError):
                getattr(instance, method)("")


class TestVoucherTransaction:
    def test_issue_is_positive(self):
        txn = VoucherTransaction.issue(
            voucher_instance_id=new_uuid(), amount=Decimal("500"), operation_id=new_uuid())
        assert txn.amount == Decimal("500")

    def test_redeem_requires_negative(self):
        with pytest.raises(InvalidVoucherTransactionAmountError):
            VoucherTransaction.redeem(
                voucher_instance_id=new_uuid(), amount=Decimal("50"), operation_id=new_uuid())

    def test_reserve_starts_reserved(self):
        txn = VoucherTransaction.reserve(
            voucher_instance_id=new_uuid(), amount=Decimal("-100"), operation_id=new_uuid())
        assert txn.status.value == "RESERVED"

    def test_release_of_offsets_reservation(self):
        reservation = VoucherTransaction.reserve(
            voucher_instance_id=new_uuid(), amount=Decimal("-100"), operation_id=new_uuid())
        release = VoucherTransaction.release_of(reservation, operation_id=new_uuid())
        assert release.amount == Decimal("100")

    def test_reversal_flips_sign(self):
        issue = VoucherTransaction.issue(
            voucher_instance_id=new_uuid(), amount=Decimal("500"), operation_id=new_uuid())
        reversal = VoucherTransaction.reversal_of(
            issue, operation_id=new_uuid(), reason_code="ERROR")
        assert reversal.amount == Decimal("-500")

    def test_cannot_reverse_twice(self):
        issue = VoucherTransaction.issue(
            voucher_instance_id=new_uuid(), amount=Decimal("500"), operation_id=new_uuid())
        reversal = VoucherTransaction.reversal_of(issue, operation_id=new_uuid(), reason_code="x")
        issue.mark_reversed(reversal.id)
        with pytest.raises(InvalidVoucherTransactionStateError):
            VoucherTransaction.reversal_of(issue, operation_id=new_uuid(), reason_code="y")


class TestVoucherBalancePolicy:
    def test_partial_redemption_sequence(self):
        instance_id = new_uuid()
        issue = VoucherTransaction.issue(
            voucher_instance_id=instance_id, amount=Decimal("500"), operation_id=new_uuid())
        redeem1 = VoucherTransaction.redeem(
            voucher_instance_id=instance_id, amount=Decimal("-200"), operation_id=new_uuid())
        redeem2 = VoucherTransaction.redeem(
            voucher_instance_id=instance_id, amount=Decimal("-100"), operation_id=new_uuid())
        ledger = [issue, redeem1, redeem2]
        assert VoucherBalancePolicy.balance(ledger) == Decimal("200")

    def test_reservation_reduces_balance_immediately(self):
        instance_id = new_uuid()
        issue = VoucherTransaction.issue(
            voucher_instance_id=instance_id, amount=Decimal("500"), operation_id=new_uuid())
        reservation = VoucherTransaction.reserve(
            voucher_instance_id=instance_id, amount=Decimal("-150"), operation_id=new_uuid())
        ledger = [issue, reservation]
        assert VoucherBalancePolicy.balance(ledger) == Decimal("350")
        assert VoucherBalancePolicy.reserved_amount(ledger) == Decimal("150")

    def test_reload_increases_balance(self):
        instance_id = new_uuid()
        issue = VoucherTransaction.issue(
            voucher_instance_id=instance_id, amount=Decimal("100"), operation_id=new_uuid())
        reload = VoucherTransaction.reload(
            voucher_instance_id=instance_id, amount=Decimal("50"), operation_id=new_uuid())
        assert VoucherBalancePolicy.balance([issue, reload]) == Decimal("150")


class TestVoucherRedemption:
    def test_record(self):
        redemption = VoucherRedemption.record(
            new_uuid(), new_uuid(), Decimal("200.00"), new_uuid())
        assert redemption.amount_applied == Decimal("200.00")

    def test_rejects_non_positive_amount(self):
        with pytest.raises(InvalidVoucherInstanceStateError):
            VoucherRedemption.record(new_uuid(), new_uuid(), Decimal("0"), new_uuid())
