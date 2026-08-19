"""SALES-2 — Sales/POS permission gate, hot authorization and audit value
objects. Mirrors tests/unit/inventory/test_inventory_security.py's structure
(same PermissionChecker/AuthorizationPolicy/AuthorizationGrant contract)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    DenyAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.permissions import ALL_SALES_PERMISSIONS, SalesPermissions
from backend.domain.sales.exceptions import (
    InvalidSalesAuditFieldError,
    SalesConfigurationError,
    SalesPermissionDeniedError,
    SalesSegregationOfDutiesError,
)
from backend.domain.sales.value_objects.authorization_grant import AuthorizationGrant
from backend.domain.sales.value_objects.sales_audit_entry import SalesAuditEntry


class TestSalesAuthorizationPolicy:
    def test_unknown_permission_rejected(self):
        policy = SalesAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(SalesPermissionDeniedError):
            policy.require("u1", "POS.no_existe")

    def test_no_checker_is_fail_closed(self):
        policy = SalesAuthorizationPolicy()
        with pytest.raises(SalesConfigurationError):
            policy.require("u1", SalesPermissions.RETURN)

    def test_permissive_for_tests_allows_known_code(self):
        policy = SalesAuthorizationPolicy.permissive_for_tests()
        policy.require("u1", SalesPermissions.RETURN)  # does not raise

    def test_deny_all_checker_denies(self):
        policy = SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests())
        with pytest.raises(SalesPermissionDeniedError):
            policy.require("u1", SalesPermissions.RETURN)

    def test_has_permission_probe_is_fail_closed_without_checker(self):
        policy = SalesAuthorizationPolicy()
        assert policy.has_permission("u1", SalesPermissions.RETURN) is False

    def test_has_permission_probe_requires_user_id(self):
        policy = SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())
        assert policy.has_permission("", SalesPermissions.RETURN) is False

    def test_require_requires_authenticated_user(self):
        policy = SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())
        with pytest.raises(SalesPermissionDeniedError):
            policy.require("", SalesPermissions.RETURN)


class TestSalesHotAuthorization:
    def test_hot_authorization_returns_audit_grant(self):
        grant = SalesAuthorizationPolicy.permissive_for_tests().authorize_exception(
            authorizer_user_id="supervisor-1",
            requested_by="cajero-1",
            permission_code=SalesPermissions.DISCOUNT_OVERRIDE,
            operation_id="op-1",
            reason="Cliente frecuente",
            amount=Decimal("50.00"),
        )
        assert isinstance(grant, AuthorizationGrant)
        assert grant.authorized_by == "supervisor-1"
        assert grant.requested_by == "cajero-1"
        assert grant.amount == Decimal("50.00")

    def test_hot_authorization_requires_authorizer(self):
        policy = SalesAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(SalesPermissionDeniedError):
            policy.authorize_exception(
                authorizer_user_id="",
                requested_by="cajero-1",
                permission_code=SalesPermissions.DISCOUNT_OVERRIDE,
                operation_id="op-1",
                reason="motivo",
            )

    def test_hot_authorization_rejects_self_authorization(self):
        """Master prompt §62: 'cajero no autoriza su propio descuento
        protegido' — the authorizer must be a distinct user."""
        policy = SalesAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(SalesSegregationOfDutiesError):
            policy.authorize_exception(
                authorizer_user_id="cajero-1",
                requested_by="cajero-1",
                permission_code=SalesPermissions.DISCOUNT_OVERRIDE,
                operation_id="op-1",
                reason="motivo",
            )

    def test_hot_authorization_requires_authorizer_to_hold_permission(self):
        policy = SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests())
        with pytest.raises(SalesPermissionDeniedError):
            policy.authorize_exception(
                authorizer_user_id="supervisor-1",
                requested_by="cajero-1",
                permission_code=SalesPermissions.DISCOUNT_OVERRIDE,
                operation_id="op-1",
                reason="motivo",
            )

    def test_grant_requires_reason(self):
        with pytest.raises(InvalidSalesAuditFieldError):
            AuthorizationGrant(
                permission_code=SalesPermissions.PRICE_OVERRIDE,
                requested_by="cajero-1",
                authorized_by="supervisor-1",
                operation_id="op-1",
                reason="   ",
            )

    def test_grant_rejects_float_amount(self):
        with pytest.raises(InvalidSalesAuditFieldError):
            AuthorizationGrant(
                permission_code=SalesPermissions.PRICE_OVERRIDE,
                requested_by="cajero-1",
                authorized_by="supervisor-1",
                operation_id="op-1",
                reason="motivo",
                amount=12.5,
            )


class TestSalesAuditEntry:
    def test_valid_entry(self):
        entry = SalesAuditEntry(
            user_id="cajero-1",
            operation_id="op-1",
            action="SALE_COMPLETED",
            branch_id="branch-1",
        )
        assert entry.before == {}
        assert entry.after == {}
        assert entry.occurred_at

    def test_requires_branch_id(self):
        with pytest.raises(InvalidSalesAuditFieldError):
            SalesAuditEntry(
                user_id="cajero-1", operation_id="op-1", action="SALE_COMPLETED",
                branch_id="",
            )

    def test_requires_action(self):
        with pytest.raises(InvalidSalesAuditFieldError):
            SalesAuditEntry(
                user_id="cajero-1", operation_id="op-1", action="",
                branch_id="branch-1",
            )
