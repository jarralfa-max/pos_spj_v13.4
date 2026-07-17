"""FASE SUP-1 — supplier domain tests (states, blocks, policies, rating, risk)."""

from datetime import date
from decimal import Decimal

import pytest

from backend.domain.suppliers.entities import (
    Supplier,
    SupplierBankAccount,
    SupplierBlock,
    SupplierDocument,
    SupplierEvaluation,
    SupplierEvaluationItem,
    SupplierRisk,
    SupplierRiskFactor,
)
from backend.domain.suppliers.enums import (
    BankAccountStatus,
    BlockType,
    DocumentStatus,
    DocumentType,
    EvaluationDimension,
    RatingGrade,
    RiskLevel,
    SupplierStatus,
)
from backend.domain.suppliers.exceptions import (
    BankAccountNotVerifiedError,
    InvalidSupplierStateError,
    RejectedSupplierReactivationError,
    SegregationOfDutiesError,
    SupplierBlockedError,
)
from backend.domain.suppliers.policies import (
    SupplierApprovalPolicy,
    SupplierDuplicatePolicy,
    SupplierPaymentPolicy,
)
from backend.domain.suppliers.value_objects import (
    Money,
    PaymentTerms,
    RatingBands,
    SupplierCode,
    SupplierRating,
    TaxIdentifier,
)
from backend.shared.ids import new_uuid


def _supplier(created_by="u-capturista", with_rfc=True) -> Supplier:
    return Supplier.create(
        SupplierCode.from_sequence(1), "Distribuidora del Valle SA de CV",
        trade_name="Del Valle", created_by_user_id=created_by,
        tax_identifier=TaxIdentifier("DVA010203XY1") if with_rfc else None)


class TestValueObjects:
    def test_supplier_code_format(self):
        assert str(SupplierCode.from_sequence(42)) == "PRV-000042"
        with pytest.raises(Exception):
            SupplierCode("42")

    def test_tax_identifier_person_type(self):
        assert TaxIdentifier("DVA010203XY1").person_type.value == "MORAL"   # 3 letters
        assert TaxIdentifier("DVAL010203XY1").person_type.value == "FISICA"  # 4 letters

    def test_money_rejects_float(self):
        with pytest.raises(Exception):
            Money(10.5)
        assert Money(Decimal("10.50")).to_string() == "10.50"

    def test_payment_terms_advance_requires_pct(self):
        with pytest.raises(Exception):
            PaymentTerms(advance_required=True, advance_percentage=Decimal("0"))
        assert PaymentTerms(credit_days=30).credit_days == 30


class TestStatusTransitions:
    def test_happy_path_draft_to_active(self):
        s = _supplier()
        assert s.status is SupplierStatus.DRAFT
        s.submit_for_approval()
        assert s.status is SupplierStatus.PENDING_APPROVAL
        s.approve("u-autorizador")
        assert s.status is SupplierStatus.ACTIVE
        assert s.approved_by_user_id == "u-autorizador"

    def test_cannot_submit_without_rfc(self):
        s = _supplier(with_rfc=False)
        with pytest.raises(InvalidSupplierStateError):
            s.submit_for_approval()

    def test_reject_then_cannot_activate(self):
        s = _supplier()
        s.submit_for_approval()
        s.reject("u-autorizador", "datos incompletos")
        assert s.status is SupplierStatus.REJECTED
        with pytest.raises(RejectedSupplierReactivationError):
            s.activate()

    def test_suspend_and_reactivate(self):
        s = _supplier()
        s.submit_for_approval(); s.approve("u2")
        s.suspend("revisión de documentos")
        assert s.status is SupplierStatus.SUSPENDED
        s.activate()
        assert s.status is SupplierStatus.ACTIVE

    def test_deactivate_preserves_history_no_delete(self):
        s = _supplier()
        s.submit_for_approval(); s.approve("u2")
        s.has_history = True
        s.deactivate()
        assert s.status is SupplierStatus.INACTIVE
        with pytest.raises(Exception):
            s.assert_deletable()

    def test_cannot_approve_from_draft(self):
        with pytest.raises(InvalidSupplierStateError):
            _supplier().approve("u2")


class TestBlocks:
    def _active(self):
        s = _supplier()
        s.submit_for_approval(); s.approve("u2")
        return s

    def test_purchasing_block_stops_purchase_only(self):
        s = self._active()
        s.apply_block(SupplierBlock.create(
            s.id, BlockType.PURCHASING_BLOCK, "adeudo", "u3", new_uuid()))
        assert not s.can_purchase()
        assert s.can_pay()       # payments of prior invoices still allowed
        assert s.can_receive()

    def test_payment_block_stops_pay_only(self):
        s = self._active()
        s.apply_block(SupplierBlock.create(
            s.id, BlockType.PAYMENT_BLOCK, "banco sin verificar", "u3", new_uuid()))
        assert not s.can_pay()
        assert s.can_purchase()

    def test_general_block_sets_blocked_status(self):
        s = self._active()
        s.apply_block(SupplierBlock.create(
            s.id, BlockType.GENERAL_BLOCK, "fraude", "u3", new_uuid()))
        assert s.status is SupplierStatus.BLOCKED
        assert not s.can_purchase() and not s.can_receive() and not s.can_pay()

    def test_unblock_general_restores_active(self):
        s = self._active()
        s.apply_block(SupplierBlock.create(
            s.id, BlockType.GENERAL_BLOCK, "x", "u3", new_uuid()))
        s.remove_block(BlockType.GENERAL_BLOCK)
        assert s.status is SupplierStatus.ACTIVE

    def test_block_requires_reason(self):
        with pytest.raises(InvalidSupplierStateError):
            SupplierBlock.create(new_uuid(), BlockType.QUALITY_BLOCK, "  ", "u3", new_uuid())


class TestApprovalPolicy:
    def test_creator_cannot_approve(self):
        s = _supplier(created_by="u-same")
        s.submit_for_approval()
        with pytest.raises(SegregationOfDutiesError):
            SupplierApprovalPolicy().enforce_can_approve(s, "u-same")

    def test_other_user_can_approve(self):
        s = _supplier(created_by="u-a")
        s.submit_for_approval()
        SupplierApprovalPolicy().enforce_can_approve(s, "u-b")  # no raise


class TestBankVerificationPolicy:
    def test_unverified_account_cannot_pay(self):
        s = _supplier(); s.submit_for_approval(); s.approve("u2")
        acct = SupplierBankAccount.create(s.id, "BBVA", "Del Valle", clabe="012345678901234561")
        with pytest.raises(BankAccountNotVerifiedError):
            SupplierPaymentPolicy().enforce_can_pay(s, acct)

    def test_verified_account_can_pay(self):
        s = _supplier(); s.submit_for_approval(); s.approve("u2")
        acct = SupplierBankAccount.create(s.id, "BBVA", "Del Valle")
        acct.submit_for_verification()
        acct.verify("u-tesoreria")
        SupplierPaymentPolicy().enforce_can_pay(s, acct)  # no raise

    def test_change_invalidates_verification(self):
        acct = SupplierBankAccount.create(new_uuid(), "BBVA", "Del Valle")
        acct.verify("u-tesoreria")
        assert acct.status is BankAccountStatus.VERIFIED
        acct.invalidate_on_change()
        assert acct.status is BankAccountStatus.PENDING_VERIFICATION
        with pytest.raises(BankAccountNotVerifiedError):
            acct.assert_usable_for_payment()

    def test_clabe_is_masked(self):
        acct = SupplierBankAccount.create(new_uuid(), "BBVA", "X", clabe="012345678901231234")
        masked = acct.masked_clabe()
        assert masked.endswith("1234") and "•" in masked and "0123456789" not in masked


class TestDuplicatePolicy:
    def test_detects_matches_never_merges(self):
        existing = [{"id": "s1", "tax_identifier": "DVA010203XY1",
                     "legal_name": "Distribuidora del Valle SA de CV",
                     "trade_name": "", "phone_e164": "+525511112222",
                     "email": "ventas@delvalle.mx", "clabe": "", "account_number": ""}]
        cand = {"tax_identifier": "dva010203xy1", "legal_name": "DISTRIBUIDORA DEL VALLE SA DE CV",
                "phone_e164": "5511112222"}
        matches = SupplierDuplicatePolicy().find_matches(cand, existing)
        assert matches and matches[0].supplier_id == "s1"
        assert "Mismo RFC" in matches[0].reasons

    def test_no_false_positive(self):
        existing = [{"id": "s1", "tax_identifier": "AAA010203XY1",
                     "legal_name": "Otra Empresa", "trade_name": "",
                     "phone_e164": "", "email": "", "clabe": "", "account_number": ""}]
        cand = {"tax_identifier": "BBB010203XY1", "legal_name": "Distinta"}
        assert SupplierDuplicatePolicy().find_matches(cand, existing) == []


class TestRating:
    def test_score_to_grade_with_configurable_bands(self):
        assert SupplierRating.from_score(95).grade is RatingGrade.A
        assert SupplierRating.from_score(85).grade is RatingGrade.B
        assert SupplierRating.from_score(72).grade is RatingGrade.C
        assert SupplierRating.from_score(50).grade is RatingGrade.D
        strict = RatingBands(a_min=95, b_min=88, c_min=75)
        assert SupplierRating.from_score(90, strict).grade is RatingGrade.B

    def test_evaluation_weighted_score(self):
        items = [
            SupplierEvaluationItem(EvaluationDimension.QUALITY, 90, Decimal("2")),
            SupplierEvaluationItem(EvaluationDimension.PRICE, 60, Decimal("1")),
        ]
        ev = SupplierEvaluation.create(new_uuid(), "2026-07", items, "u-eval")
        assert ev.score == 80  # (90*2 + 60*1) / 3
        assert ev.rating.grade is RatingGrade.B

    def test_evaluation_requires_items(self):
        with pytest.raises(Exception):
            SupplierEvaluation.create(new_uuid(), "2026-07", [], "u-eval")


class TestRisk:
    def test_risk_explains_causes(self):
        risk = SupplierRisk(
            supplier_id=new_uuid(), level=RiskLevel.HIGH,
            factors=[SupplierRiskFactor("LATE", "3 entregas tardías en 30 días"),
                     SupplierRiskFactor("DOC", "Opinión de cumplimiento vencida")])
        causes = risk.explanation()
        assert len(causes) == 2 and "tardías" in causes[0]


class TestDocumentStatus:
    def test_expiring_and_expired(self):
        today = date(2026, 7, 17)
        valid = SupplierDocument.create(new_uuid(), DocumentType.INSURANCE, "f",
                                        status=DocumentStatus.VALID, expires_at=date(2027, 1, 1))
        assert valid.compute_status(today) is DocumentStatus.VALID
        soon = SupplierDocument.create(new_uuid(), DocumentType.INSURANCE, "f",
                                       status=DocumentStatus.VALID, expires_at=date(2026, 8, 1))
        assert soon.compute_status(today) is DocumentStatus.EXPIRING
        gone = SupplierDocument.create(new_uuid(), DocumentType.INSURANCE, "f",
                                       status=DocumentStatus.VALID, expires_at=date(2026, 6, 1))
        assert gone.compute_status(today) is DocumentStatus.EXPIRED
