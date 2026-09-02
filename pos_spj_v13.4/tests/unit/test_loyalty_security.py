"""LOY-1 — Fidelidad/Loyalty permission gate, hot authorization and audit
value objects. Mirrors tests/unit/test_sales_security.py's structure (same
PermissionChecker/AuthorizationPolicy/AuthorizationGrant contract)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import (
    AllowAllLoyaltyPermissionCheckerForTests,
    DenyAllLoyaltyPermissionCheckerForTests,
    LoyaltyAuthorizationPolicy,
)
from backend.application.loyalty.permissions import ALL_LOYALTY_PERMISSIONS, LoyaltyPermissions
from backend.domain.loyalty.exceptions import (
    InvalidLoyaltyAuditFieldError,
    LoyaltyConfigurationError,
    LoyaltyPermissionDeniedError,
    LoyaltySegregationOfDutiesError,
)
from backend.domain.loyalty.value_objects.authorization_grant import AuthorizationGrant
from backend.domain.loyalty.value_objects.loyalty_audit_entry import LoyaltyAuditEntry


class TestLoyaltyAuthorizationPolicy:
    def test_unknown_permission_rejected(self):
        policy = LoyaltyAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(LoyaltyPermissionDeniedError):
            policy.require("u1", "GROWTH_ENGINE.no_existe")

    def test_no_checker_is_fail_closed(self):
        policy = LoyaltyAuthorizationPolicy()
        with pytest.raises(LoyaltyConfigurationError):
            policy.require("u1", LoyaltyPermissions.POINTS_ADJUST)

    def test_permissive_for_tests_allows_known_code(self):
        policy = LoyaltyAuthorizationPolicy.permissive_for_tests()
        policy.require("u1", LoyaltyPermissions.POINTS_ADJUST)  # does not raise

    def test_deny_all_checker_denies(self):
        policy = LoyaltyAuthorizationPolicy(DenyAllLoyaltyPermissionCheckerForTests())
        with pytest.raises(LoyaltyPermissionDeniedError):
            policy.require("u1", LoyaltyPermissions.POINTS_ADJUST)

    def test_has_permission_probe_is_fail_closed_without_checker(self):
        policy = LoyaltyAuthorizationPolicy()
        assert policy.has_permission("u1", LoyaltyPermissions.POINTS_ADJUST) is False

    def test_has_permission_probe_requires_user_id(self):
        policy = LoyaltyAuthorizationPolicy(AllowAllLoyaltyPermissionCheckerForTests())
        assert policy.has_permission("", LoyaltyPermissions.POINTS_ADJUST) is False

    def test_require_requires_authenticated_user(self):
        policy = LoyaltyAuthorizationPolicy(AllowAllLoyaltyPermissionCheckerForTests())
        with pytest.raises(LoyaltyPermissionDeniedError):
            policy.require("", LoyaltyPermissions.POINTS_ADJUST)


class TestLoyaltyHotAuthorization:
    def test_hot_authorization_returns_audit_grant(self):
        grant = LoyaltyAuthorizationPolicy.permissive_for_tests().authorize_exception(
            authorizer_user_id="supervisor-1",
            requested_by="operador-1",
            permission_code=LoyaltyPermissions.POINTS_ADJUST,
            operation_id="op-1",
            reason="Ajuste por reclamo de cliente",
            amount=Decimal("50.00"),
        )
        assert isinstance(grant, AuthorizationGrant)
        assert grant.authorized_by == "supervisor-1"
        assert grant.requested_by == "operador-1"
        assert grant.amount == Decimal("50.00")

    def test_hot_authorization_requires_authorizer(self):
        policy = LoyaltyAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(LoyaltyPermissionDeniedError):
            policy.authorize_exception(
                authorizer_user_id="",
                requested_by="operador-1",
                permission_code=LoyaltyPermissions.POINTS_ADJUST,
                operation_id="op-1",
                reason="motivo",
            )

    def test_hot_authorization_rejects_self_authorization(self):
        """Master prompt §60: 'quien ajusta puntos no aprueba su propio
        ajuste' — the authorizer must be a distinct user."""
        policy = LoyaltyAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(LoyaltySegregationOfDutiesError):
            policy.authorize_exception(
                authorizer_user_id="operador-1",
                requested_by="operador-1",
                permission_code=LoyaltyPermissions.POINTS_ADJUST,
                operation_id="op-1",
                reason="motivo",
            )

    def test_hot_authorization_requires_authorizer_to_hold_permission(self):
        policy = LoyaltyAuthorizationPolicy(DenyAllLoyaltyPermissionCheckerForTests())
        with pytest.raises(LoyaltyPermissionDeniedError):
            policy.authorize_exception(
                authorizer_user_id="supervisor-1",
                requested_by="operador-1",
                permission_code=LoyaltyPermissions.POINTS_ADJUST,
                operation_id="op-1",
                reason="motivo",
            )

    def test_grant_requires_reason(self):
        with pytest.raises(InvalidLoyaltyAuditFieldError):
            AuthorizationGrant(
                permission_code=LoyaltyPermissions.CAMPAIGN_ACTIVATE,
                requested_by="operador-1",
                authorized_by="supervisor-1",
                operation_id="op-1",
                reason="   ",
            )

    def test_grant_rejects_float_amount(self):
        with pytest.raises(InvalidLoyaltyAuditFieldError):
            AuthorizationGrant(
                permission_code=LoyaltyPermissions.CAMPAIGN_ACTIVATE,
                requested_by="operador-1",
                authorized_by="supervisor-1",
                operation_id="op-1",
                reason="motivo",
                amount=12.5,
            )


class TestLoyaltyAuditEntry:
    def test_valid_entry(self):
        entry = LoyaltyAuditEntry(
            user_id="operador-1",
            operation_id="op-1",
            action="POINTS_ADJUSTED",
            branch_id="branch-1",
        )
        assert entry.before == {}
        assert entry.after == {}
        assert entry.occurred_at

    def test_requires_branch_id(self):
        with pytest.raises(InvalidLoyaltyAuditFieldError):
            LoyaltyAuditEntry(
                user_id="operador-1", operation_id="op-1", action="POINTS_ADJUSTED",
                branch_id="",
            )

    def test_requires_action(self):
        with pytest.raises(InvalidLoyaltyAuditFieldError):
            LoyaltyAuditEntry(
                user_id="operador-1", operation_id="op-1", action="",
                branch_id="branch-1",
            )


def test_all_loyalty_permissions_frozenset_matches_class_attrs():
    assert LoyaltyPermissions.POINTS_ADJUST in ALL_LOYALTY_PERMISSIONS
    assert LoyaltyPermissions.SWEEPSTAKES_DRAW in ALL_LOYALTY_PERMISSIONS
    assert LoyaltyPermissions.COUPON_OVERRIDE in ALL_LOYALTY_PERMISSIONS
