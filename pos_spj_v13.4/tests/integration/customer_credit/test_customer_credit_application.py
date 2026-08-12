"""CRM-8 — Customer Credit application tests (use cases + query services).

Covers happy path, permission-denied (fail closed), invalid state,
idempotency, rollback, audit, segregation of duties (requester != approver),
the hot-authorization override path, the read-only CxC summary against the
legacy `cuentas_por_cobrar` table, FieldVisibility masking, and the credit
sale eligibility gate.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.application.customers.authorization import (
    CustomerAuthorizationPolicy,
    DenyAllCustomerPermissionCheckerForTests,
)
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customer_credit.queries.customer_accounts_receivable_summary_query import (
    CustomerAccountsReceivableSummaryQuery,
)
from backend.application.customer_credit.queries.customer_credit_query_service import (
    CustomerCreditQueryService,
)
from backend.application.customer_credit.use_cases.check_credit_sale_eligibility_use_case import (
    CheckCreditSaleEligibilityUseCase,
)
from backend.application.customer_credit.use_cases.customer_credit_use_cases import (
    ApproveCustomerCreditUseCase,
    BlockCustomerCreditUseCase,
    CloseCustomerCreditUseCase,
    RejectCustomerCreditUseCase,
    ReopenCustomerCreditUseCase,
    RequestCustomerCreditUseCase,
    ReviewCustomerCreditUseCase,
    SuspendCustomerCreditUseCase,
    UpdateCustomerCreditLimitUseCase,
)
from backend.domain.customers.exceptions import CustomerPermissionDeniedError
from backend.domain.customers.value_objects.field_visibility import FieldVisibility
from backend.shared.ids import new_uuid


def _allow():
    return CustomerAuthorizationPolicy.permissive_for_tests()


def _deny():
    return CustomerAuthorizationPolicy(DenyAllCustomerPermissionCheckerForTests())


def _request(conn, *, actor="u-vendedor", customer_id="cust-1", requested_limit="5000",
             payment_terms_days=15, operation_id=None):
    return RequestCustomerCreditUseCase(_allow()).execute(
        conn, actor_user_id=actor, customer_id=customer_id, operation_id=operation_id or new_uuid(),
        requested_limit=requested_limit, payment_terms_days=payment_terms_days)


def _authorized(conn, *, customer_id="cust-1", requester="u-vendedor", approver="u-gerente",
                limit="8000"):
    _request(conn, actor=requester, customer_id=customer_id)
    ReviewCustomerCreditUseCase(_allow()).execute(
        conn, actor_user_id="u-analista", customer_id=customer_id, operation_id=new_uuid())
    return ApproveCustomerCreditUseCase(_allow()).execute(
        conn, actor_user_id=approver, customer_id=customer_id, operation_id=new_uuid(),
        credit_limit=limit)


class TestRequest:
    def test_happy_path(self, cc_conn):
        result = _request(cc_conn)
        assert result.success

    def test_permission_denied(self, cc_conn):
        result = RequestCustomerCreditUseCase(_deny()).execute(
            cc_conn, actor_user_id="u1", customer_id="cust-1", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_idempotent_on_operation_id(self, cc_conn):
        op_id = new_uuid()
        first = _request(cc_conn, operation_id=op_id)
        second = _request(cc_conn, operation_id=op_id)
        assert first.entity_id == second.entity_id
        count = cc_conn.execute("SELECT COUNT(*) FROM customer_credit_profiles").fetchone()[0]
        assert count == 1

    def test_second_request_for_same_customer_is_rejected(self, cc_conn):
        _request(cc_conn)
        second = _request(cc_conn)
        assert not second.success and second.error_code == "VALIDATION"


class TestApproveSegregationOfDuties:
    def test_requester_cannot_self_approve(self, cc_conn):
        _request(cc_conn, actor="u-vendedor")
        ReviewCustomerCreditUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-analista", customer_id="cust-1", operation_id=new_uuid())
        result = ApproveCustomerCreditUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-vendedor", customer_id="cust-1", operation_id=new_uuid(),
            credit_limit="8000")
        assert not result.success and result.error_code == "SEGREGATION_OF_DUTIES"

    def test_distinct_approver_succeeds(self, cc_conn):
        result = _authorized(cc_conn)
        assert result.success
        assert result.data["credit_limit"] == "8000"

    def test_approve_requires_under_review_status(self, cc_conn):
        _request(cc_conn, actor="u-vendedor")
        result = ApproveCustomerCreditUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-gerente", customer_id="cust-1", operation_id=new_uuid(),
            credit_limit="8000")
        assert not result.success and result.error_code == "VALIDATION"


class TestUpdateLimitAndOverride:
    def test_routine_update_requires_limit_edit_permission(self, cc_conn):
        _authorized(cc_conn)
        result = UpdateCustomerCreditLimitUseCase(_deny()).execute(
            cc_conn, actor_user_id="u-gerente", customer_id="cust-1", new_limit="9000",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_routine_update_succeeds(self, cc_conn):
        _authorized(cc_conn)
        result = UpdateCustomerCreditLimitUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-gerente", customer_id="cust-1", new_limit="9000",
            operation_id=new_uuid())
        assert result.success and result.data["credit_limit"] == "9000"

    def test_override_requires_distinct_authorizer(self, cc_conn):
        _authorized(cc_conn)
        # authorize_exception() raises InvalidAuthorizationError via
        # CustomerAuthorizationGrant's own invariant when authorizer ==
        # requester; the use case catches CustomerDomainError (its parent)
        # and converts it to a failed result, same as every other
        # permission-shaped failure in this bounded context — it never lets
        # a raw domain exception escape to the caller.
        result = UpdateCustomerCreditLimitUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-gerente", customer_id="cust-1", new_limit="90000",
            operation_id=new_uuid(), override=True, requested_by_user_id="u-gerente",
            reason="aumento extraordinario")
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_override_with_distinct_authorizer_succeeds_and_is_audited(self, cc_conn):
        _authorized(cc_conn)
        result = UpdateCustomerCreditLimitUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-director", customer_id="cust-1", new_limit="90000",
            operation_id=new_uuid(), override=True, requested_by_user_id="u-gerente",
            reason="cliente estratégico, aumento extraordinario")
        assert result.success and result.data["credit_limit"] == "90000"
        from backend.infrastructure.db.repositories.customer_credit.unit_of_work import (
            CustomerCreditUnitOfWork,
        )
        with CustomerCreditUnitOfWork(cc_conn) as uow:
            audit = uow.audit.list_for_customer("cust-1")
        overridden = [a for a in audit if a["action"] == "CUSTOMER_CREDIT_LIMIT_OVERRIDDEN"]
        assert len(overridden) == 1
        assert overridden[0]["authorized_by_user_id"] == "u-director"

    def test_override_requires_reason(self, cc_conn):
        _authorized(cc_conn)
        result = UpdateCustomerCreditLimitUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-director", customer_id="cust-1", new_limit="90000",
            operation_id=new_uuid(), override=True, requested_by_user_id="u-gerente",
            reason="")
        assert not result.success and result.error_code == "PERMISSION_DENIED"


class TestOtherLifecycleTransitions:
    def test_reject_when_no_credit_limit_offered(self, cc_conn):
        _request(cc_conn)
        result = RejectCustomerCreditUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-analista", customer_id="cust-1", operation_id=new_uuid(),
            reason="documentación insuficiente")
        assert result.success

    def test_suspend_block_reopen_close_cycle(self, cc_conn):
        _authorized(cc_conn)
        assert SuspendCustomerCreditUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-gerente", customer_id="cust-1", operation_id=new_uuid(),
            reason="pago atrasado").success
        assert BlockCustomerCreditUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-gerente", customer_id="cust-1", operation_id=new_uuid(),
            reason="cobranza").success
        assert ReopenCustomerCreditUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-gerente", customer_id="cust-1", operation_id=new_uuid(),
            reason="regularizado").success
        assert CloseCustomerCreditUseCase(_allow()).execute(
            cc_conn, actor_user_id="u-gerente", customer_id="cust-1", operation_id=new_uuid(),
            reason="cliente cerró cuenta").success

    def test_missing_profile_returns_not_found(self, cc_conn):
        result = SuspendCustomerCreditUseCase(_allow()).execute(
            cc_conn, actor_user_id="u1", customer_id="does-not-exist", operation_id=new_uuid(),
            reason="x")
        assert not result.success and result.error_code == "NOT_FOUND"


class TestCustomerAccountsReceivableSummaryQuery:
    def test_computes_exposure_from_legacy_cxc_table(self, cc_conn):
        cc_conn.execute(
            "INSERT INTO cuentas_por_cobrar (id, cliente_id, monto_original, saldo_pendiente, estado, fecha)"
            " VALUES ('cxc1','cust-1',1500.50,1500.50,'pendiente','2026-01-01 10:00:00')")
        cc_conn.commit()
        query = CustomerAccountsReceivableSummaryQuery(cc_conn)
        summary = query.get_summary("cust-1", payment_terms_days=15,
                                    as_of=date(2026, 1, 5))
        assert summary.current_exposure == Decimal("1500.50")
        assert summary.overdue_amount == Decimal("0")  # due 2026-01-16, not yet
        assert summary.next_due_date == date(2026, 1, 16)

    def test_overdue_when_past_due_date(self, cc_conn):
        cc_conn.execute(
            "INSERT INTO cuentas_por_cobrar (id, cliente_id, monto_original, saldo_pendiente, estado, fecha)"
            " VALUES ('cxc1','cust-1',1000,1000,'pendiente','2026-01-01 10:00:00')")
        cc_conn.commit()
        query = CustomerAccountsReceivableSummaryQuery(cc_conn)
        summary = query.get_summary("cust-1", payment_terms_days=15,
                                    as_of=date(2026, 2, 1))
        assert summary.overdue_amount == Decimal("1000")
        assert summary.next_due_date is None

    def test_paid_documents_excluded(self, cc_conn):
        cc_conn.execute(
            "INSERT INTO cuentas_por_cobrar (id, cliente_id, monto_original, saldo_pendiente, estado, fecha)"
            " VALUES ('cxc1','cust-1',1000,1000,'pagado','2026-01-01 10:00:00')")
        cc_conn.commit()
        query = CustomerAccountsReceivableSummaryQuery(cc_conn)
        summary = query.get_summary("cust-1", payment_terms_days=15)
        assert summary.current_exposure == Decimal("0")
        assert summary.open_documents_count == 0

    def test_other_customers_not_mixed_in(self, cc_conn):
        cc_conn.execute(
            "INSERT INTO cuentas_por_cobrar (id, cliente_id, monto_original, saldo_pendiente, estado, fecha)"
            " VALUES ('cxc1','cust-2',999,999,'pendiente','2026-01-01 10:00:00')")
        cc_conn.commit()
        query = CustomerAccountsReceivableSummaryQuery(cc_conn)
        summary = query.get_summary("cust-1", payment_terms_days=15)
        assert summary.current_exposure == Decimal("0")

    def test_no_rows_returns_zeroed_summary(self, cc_conn):
        query = CustomerAccountsReceivableSummaryQuery(cc_conn)
        summary = query.get_summary("cust-nonexistent", payment_terms_days=30)
        assert summary.current_exposure == Decimal("0")
        assert summary.overdue_amount == Decimal("0")
        assert summary.next_due_date is None
        assert summary.open_documents_count == 0


class TestCustomerCreditQueryService:
    def test_view_only_permission_masks_amounts(self, cc_conn):
        _authorized(cc_conn, limit="12345")
        checker_grants = {CustomerPermissions.CREDIT_VIEW}

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        service = CustomerCreditQueryService(cc_conn, CustomerAuthorizationPolicy(_Checker()))
        view = service.get_summary("cust-1", actor_user_id="u1")
        assert view.visibility is FieldVisibility.MASKED
        assert "1" not in view.credit_limit  # fully masked with bullets
        assert view.status == "AUTHORIZED"  # status itself is never masked

    def test_sensitive_permission_reveals_full_amounts(self, cc_conn):
        _authorized(cc_conn, limit="12345")
        checker_grants = {CustomerPermissions.CREDIT_VIEW, CustomerPermissions.CREDIT_VIEW_SENSITIVE}

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        service = CustomerCreditQueryService(cc_conn, CustomerAuthorizationPolicy(_Checker()))
        view = service.get_summary("cust-1", actor_user_id="u1")
        assert view.visibility is FieldVisibility.VISIBLE
        assert view.credit_limit == "12345"

    def test_no_profile_reports_not_configured(self, cc_conn):
        service = CustomerCreditQueryService(cc_conn, _allow())
        view = service.get_summary("cust-nonexistent", actor_user_id="u1")
        assert view.status == "NOT_CONFIGURED"

    def test_permission_denied_without_credit_view(self, cc_conn):
        service = CustomerCreditQueryService(cc_conn, _deny())
        with pytest.raises(CustomerPermissionDeniedError):
            service.get_summary("cust-1", actor_user_id="u1")


class TestCheckCreditSaleEligibility:
    def test_eligible_within_available_credit(self, cc_conn):
        _authorized(cc_conn, limit="10000")
        result = CheckCreditSaleEligibilityUseCase(_allow()).execute(
            cc_conn, actor_user_id="u1", customer_id="cust-1", amount="2000",
            operation_id=new_uuid())
        assert result.success

    def test_not_eligible_exceeding_available_credit(self, cc_conn):
        _authorized(cc_conn, limit="1000")
        cc_conn.execute(
            "INSERT INTO cuentas_por_cobrar (id, cliente_id, monto_original, saldo_pendiente, estado, fecha)"
            " VALUES ('cxc1','cust-1',900,900,'pendiente',datetime('now'))")
        cc_conn.commit()
        result = CheckCreditSaleEligibilityUseCase(_allow()).execute(
            cc_conn, actor_user_id="u1", customer_id="cust-1", amount="500",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "NOT_ELIGIBLE"
        assert any("disponible" in v for v in result.data["violations"])

    def test_public_customer_never_eligible(self, cc_conn):
        _authorized(cc_conn)
        result = CheckCreditSaleEligibilityUseCase(_allow()).execute(
            cc_conn, actor_user_id="u1", customer_id="cust-1", amount="500",
            operation_id=new_uuid(), is_public_customer=True)
        assert not result.success and result.error_code == "NOT_ELIGIBLE"

    def test_no_profile_at_all_not_eligible(self, cc_conn):
        result = CheckCreditSaleEligibilityUseCase(_allow()).execute(
            cc_conn, actor_user_id="u1", customer_id="cust-nonexistent", amount="500",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "NOT_ELIGIBLE"
