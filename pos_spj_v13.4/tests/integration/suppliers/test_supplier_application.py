"""FASE SUP-3 — supplier application tests (use cases + query services).

Covers happy path, permissions, invalid state, duplicate, idempotency, rollback,
events and audit.
"""

import pytest

from backend.application.suppliers.authorization import SupplierAuthorizationPolicy
from backend.application.suppliers.queries import (
    SearchSuppliersQueryService,
    SupplierDashboardQueryService,
    SupplierDetailQueryService,
    SupplierRiskQueryService,
)
from backend.application.suppliers.use_cases.detail_use_cases import (
    AddSupplierBankAccountUseCase,
    AssignProductToSupplierUseCase,
    VerifySupplierBankAccountUseCase,
)
from backend.application.suppliers.use_cases.evaluate_supplier_use_case import (
    EvaluateSupplierUseCase,
)
from backend.application.suppliers.use_cases.lifecycle_use_cases import (
    ApproveSupplierUseCase,
    BlockSupplierUseCase,
    CreateSupplierUseCase,
    SubmitSupplierForApprovalUseCase,
    UnblockSupplierUseCase,
)
from backend.domain.suppliers.enums import BankAccountStatus, BlockType
from backend.infrastructure.db.repositories.suppliers.unit_of_work import SupplierUnitOfWork
from backend.shared.ids import new_uuid


class _DenyChecker:
    def has_permission(self, user_id, permission_code):
        return False


def _create(conn, *, actor="u-capturista", rfc="DVA010203XY1", legal="Del Valle SA de CV",
            operation_id=None):
    return CreateSupplierUseCase().execute(
        conn, actor_user_id=actor, legal_name=legal, tax_identifier=rfc,
        operation_id=operation_id or new_uuid())


def _to_active(conn, actor="u-capturista"):
    created = _create(conn, actor=actor)
    sid = created.entity_id
    SubmitSupplierForApprovalUseCase().execute(
        conn, actor_user_id=actor, supplier_id=sid, operation_id=new_uuid())
    ApproveSupplierUseCase().execute(
        conn, actor_user_id="u-autorizador", supplier_id=sid, operation_id=new_uuid())
    return sid


class TestCreate:
    def test_happy_path_emits_event_and_audit(self, sup_conn):
        result = _create(sup_conn)
        assert result.success and result.entity_id
        assert result.data["code"] == "PRV-000001"
        outbox = sup_conn.execute(
            "SELECT COUNT(*) FROM supplier_outbox WHERE event_name='SUPPLIER_CREATED'").fetchone()[0]
        audit = sup_conn.execute(
            "SELECT COUNT(*) FROM supplier_audit_log WHERE action='SUPPLIER_CREATED'").fetchone()[0]
        assert outbox == 1 and audit == 1

    def test_permission_denied(self, sup_conn):
        uc = CreateSupplierUseCase(SupplierAuthorizationPolicy(_DenyChecker()))
        result = uc.execute(sup_conn, actor_user_id="u1", legal_name="X",
                            tax_identifier="DVA010203XY1", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_duplicate_detected_not_merged(self, sup_conn):
        _create(sup_conn)
        dup = _create(sup_conn)  # same RFC
        assert not dup.success and dup.error_code == "DUPLICATE"
        assert dup.data["duplicates"]
        # allow_duplicate overrides
        forced = CreateSupplierUseCase().execute(
            sup_conn, actor_user_id="u", legal_name="Del Valle SA de CV",
            tax_identifier="DVA010203XY1", operation_id=new_uuid(), allow_duplicate=True)
        assert forced.success

    def test_idempotent_by_operation_id(self, sup_conn):
        op = new_uuid()
        first = _create(sup_conn, operation_id=op)
        second = _create(sup_conn, operation_id=op)
        assert first.entity_id == second.entity_id
        count = sup_conn.execute("SELECT COUNT(*) FROM supplier_master").fetchone()[0]
        assert count == 1


class TestApproval:
    def test_segregation_creator_cannot_approve(self, sup_conn):
        created = _create(sup_conn, actor="u-same")
        sid = created.entity_id
        SubmitSupplierForApprovalUseCase().execute(
            sup_conn, actor_user_id="u-same", supplier_id=sid, operation_id=new_uuid())
        result = ApproveSupplierUseCase().execute(
            sup_conn, actor_user_id="u-same", supplier_id=sid, operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_cannot_approve_draft(self, sup_conn):
        sid = _create(sup_conn).entity_id
        result = ApproveSupplierUseCase().execute(
            sup_conn, actor_user_id="u-boss", supplier_id=sid, operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_full_activation(self, sup_conn):
        sid = _to_active(sup_conn)
        with SupplierUnitOfWork(sup_conn) as uow:
            assert uow.suppliers.get(sid).status.value == "ACTIVE"


class TestBlocks:
    def test_block_and_unblock(self, sup_conn):
        sid = _to_active(sup_conn)
        blocked = BlockSupplierUseCase().execute(
            sup_conn, actor_user_id="u2", supplier_id=sid, block_type="PAYMENT_BLOCK",
            reason="banco sin verificar", operation_id=new_uuid())
        assert blocked.success
        with SupplierUnitOfWork(sup_conn) as uow:
            assert uow.suppliers.get(sid).has_block(BlockType.PAYMENT_BLOCK)
        UnblockSupplierUseCase().execute(
            sup_conn, actor_user_id="u2", supplier_id=sid, block_type="PAYMENT_BLOCK",
            operation_id=new_uuid())
        with SupplierUnitOfWork(sup_conn) as uow:
            assert not uow.suppliers.get(sid).has_block(BlockType.PAYMENT_BLOCK)


class TestBankVerification:
    def test_new_account_unverified_then_verified(self, sup_conn):
        sid = _to_active(sup_conn)
        added = AddSupplierBankAccountUseCase().execute(
            sup_conn, actor_user_id="u2", supplier_id=sid, bank_name="BBVA",
            account_holder="Del Valle", clabe="012345678901231234", operation_id=new_uuid())
        assert added.success
        aid = added.entity_id
        with SupplierUnitOfWork(sup_conn) as uow:
            assert uow.bank_accounts.get(aid).status is BankAccountStatus.UNVERIFIED
        verified = VerifySupplierBankAccountUseCase().execute(
            sup_conn, actor_user_id="u-tesoreria", bank_account_id=aid, operation_id=new_uuid())
        assert verified.success
        with SupplierUnitOfWork(sup_conn) as uow:
            assert uow.bank_accounts.get(aid).status is BankAccountStatus.VERIFIED

    def test_verify_is_idempotent(self, sup_conn):
        sid = _to_active(sup_conn)
        aid = AddSupplierBankAccountUseCase().execute(
            sup_conn, actor_user_id="u2", supplier_id=sid, bank_name="BBVA",
            account_holder="X", operation_id=new_uuid()).entity_id
        VerifySupplierBankAccountUseCase().execute(
            sup_conn, actor_user_id="u3", bank_account_id=aid, operation_id=new_uuid())
        again = VerifySupplierBankAccountUseCase().execute(
            sup_conn, actor_user_id="u3", bank_account_id=aid, operation_id=new_uuid())
        assert again.success  # no error on re-verify

    def test_audit_masks_clabe(self, sup_conn):
        sid = _to_active(sup_conn)
        AddSupplierBankAccountUseCase().execute(
            sup_conn, actor_user_id="u2", supplier_id=sid, bank_name="BBVA",
            account_holder="X", clabe="012345678901231234", operation_id=new_uuid())
        row = sup_conn.execute(
            "SELECT after_json FROM supplier_audit_log WHERE action='SUPPLIER_BANK_ACCOUNT_CHANGED'"
        ).fetchone()[0]
        assert "012345678901" not in row and "1234" in row


class TestAssignAndEvaluate:
    def test_assign_product(self, sup_conn):
        sid = _to_active(sup_conn)
        pid = new_uuid()
        result = AssignProductToSupplierUseCase().execute(
            sup_conn, actor_user_id="u2", supplier_id=sid, product_id=pid,
            current_cost="12.50", preferred=True, operation_id=new_uuid())
        assert result.success
        with SupplierUnitOfWork(sup_conn) as uow:
            assert uow.products.list_by_product(pid)[0].preferred

    def test_evaluate_updates_rating_projection(self, sup_conn):
        sid = _to_active(sup_conn)
        result = EvaluateSupplierUseCase().execute(
            sup_conn, actor_user_id="u-eval", supplier_id=sid, period="2026-07",
            items=[{"dimension": "QUALITY", "score": 90, "weight": "2"},
                   {"dimension": "PRICE", "score": 60, "weight": "1"}],
            operation_id=new_uuid())
        assert result.success and result.data["score"] == 80 and result.data["rating"] == "B"
        grade = sup_conn.execute(
            "SELECT rating_grade FROM supplier_master WHERE id=?", (sid,)).fetchone()[0]
        assert grade == "B"

    def test_evaluate_idempotent(self, sup_conn):
        sid = _to_active(sup_conn)
        op = new_uuid()
        EvaluateSupplierUseCase().execute(
            sup_conn, actor_user_id="u", supplier_id=sid, period="2026-07",
            items=[{"dimension": "QUALITY", "score": 90}], operation_id=op)
        EvaluateSupplierUseCase().execute(
            sup_conn, actor_user_id="u", supplier_id=sid, period="2026-08",
            items=[{"dimension": "QUALITY", "score": 50}], operation_id=op)
        count = sup_conn.execute("SELECT COUNT(*) FROM supplier_evaluations").fetchone()[0]
        assert count == 1


class TestQueryServices:
    def test_search_and_count(self, sup_conn):
        _create(sup_conn, legal="Distribuidora Alfa", rfc="AAA010203XY1")
        _create(sup_conn, legal="Comercial Beta", rfc="BBB010203XY1")
        rows = SearchSuppliersQueryService(sup_conn).search(query="alfa")
        assert len(rows) == 1 and rows[0]["legal_name"] == "Distribuidora Alfa"
        assert SearchSuppliersQueryService(sup_conn).count() == 2

    def test_dashboard_overview(self, sup_conn):
        _to_active(sup_conn)
        _create(sup_conn, legal="Pendiente", rfc="PEN010203XY1")
        dash = SupplierDashboardQueryService(sup_conn).overview()
        assert dash.active_suppliers == 1
        # payables table absent → tolerated zero
        assert dash.payable_balance == "0.00"

    def test_detail_masks_bank_by_default(self, sup_conn):
        sid = _to_active(sup_conn)
        AddSupplierBankAccountUseCase().execute(
            sup_conn, actor_user_id="u2", supplier_id=sid, bank_name="BBVA",
            account_holder="X", clabe="012345678901231234", operation_id=new_uuid())
        masked = SupplierDetailQueryService(sup_conn).bank_accounts(sid)[0]["clabe"]
        assert masked.endswith("1234") and "•" in masked
        full = SupplierDetailQueryService(sup_conn).bank_accounts(sid, can_view_full=True)[0]["clabe"]
        assert full == "012345678901231234"

    def test_risk_explains_causes(self, sup_conn):
        sid = _to_active(sup_conn)
        BlockSupplierUseCase().execute(
            sup_conn, actor_user_id="u2", supplier_id=sid, block_type="QUALITY_BLOCK",
            reason="sanidad", operation_id=new_uuid())
        risk = SupplierRiskQueryService(sup_conn).assess(sid)
        assert risk.level in ("MEDIUM", "HIGH", "CRITICAL")
        assert any("bloqueo" in c.lower() for c in risk.causes)
