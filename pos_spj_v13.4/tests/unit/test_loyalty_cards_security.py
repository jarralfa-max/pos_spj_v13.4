"""LOY-1 — Loyalty Cards permission gate, hot authorization and audit value
objects. Mirrors tests/unit/test_loyalty_security.py's structure, but for
the specialized Loyalty Cards sub-bounded context (master prompt §30)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.loyalty_cards.authorization import (
    AllowAllLoyaltyCardsPermissionCheckerForTests,
    DenyAllLoyaltyCardsPermissionCheckerForTests,
    LoyaltyCardsAuthorizationPolicy,
)
from backend.application.loyalty_cards.permissions import (
    ALL_LOYALTY_CARDS_PERMISSIONS,
    LoyaltyCardsPermissions,
)
from backend.domain.loyalty_cards.exceptions import (
    InvalidLoyaltyCardAuditFieldError,
    LoyaltyCardConfigurationError,
    LoyaltyCardPermissionDeniedError,
    LoyaltyCardSegregationOfDutiesError,
)
from backend.domain.loyalty_cards.value_objects.authorization_grant import AuthorizationGrant
from backend.domain.loyalty_cards.value_objects.card_audit_entry import CardAuditEntry


class TestLoyaltyCardsAuthorizationPolicy:
    def test_unknown_permission_rejected(self):
        policy = LoyaltyCardsAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(LoyaltyCardPermissionDeniedError):
            policy.require("u1", "TARJETAS_FIDELIDAD.no_existe")

    def test_no_checker_is_fail_closed(self):
        policy = LoyaltyCardsAuthorizationPolicy()
        with pytest.raises(LoyaltyCardConfigurationError):
            policy.require("u1", LoyaltyCardsPermissions.BATCH_APPROVE)

    def test_permissive_for_tests_allows_known_code(self):
        policy = LoyaltyCardsAuthorizationPolicy.permissive_for_tests()
        policy.require("u1", LoyaltyCardsPermissions.BATCH_APPROVE)  # does not raise

    def test_deny_all_checker_denies(self):
        policy = LoyaltyCardsAuthorizationPolicy(DenyAllLoyaltyCardsPermissionCheckerForTests())
        with pytest.raises(LoyaltyCardPermissionDeniedError):
            policy.require("u1", LoyaltyCardsPermissions.BATCH_APPROVE)

    def test_has_permission_probe_is_fail_closed_without_checker(self):
        policy = LoyaltyCardsAuthorizationPolicy()
        assert policy.has_permission("u1", LoyaltyCardsPermissions.BATCH_APPROVE) is False

    def test_require_requires_authenticated_user(self):
        policy = LoyaltyCardsAuthorizationPolicy(AllowAllLoyaltyCardsPermissionCheckerForTests())
        with pytest.raises(LoyaltyCardPermissionDeniedError):
            policy.require("", LoyaltyCardsPermissions.BATCH_APPROVE)


class TestLoyaltyCardsHotAuthorization:
    def test_hot_authorization_returns_audit_grant(self):
        grant = LoyaltyCardsAuthorizationPolicy.permissive_for_tests().authorize_exception(
            authorizer_user_id="supervisor-1",
            requested_by="disenador-1",
            permission_code=LoyaltyCardsPermissions.TEMPLATE_ACTIVATE,
            operation_id="op-1",
            reason="Plantilla revisada por marketing",
        )
        assert isinstance(grant, AuthorizationGrant)
        assert grant.authorized_by == "supervisor-1"
        assert grant.requested_by == "disenador-1"

    def test_hot_authorization_rejects_self_authorization(self):
        """Master prompt §60: 'quien diseña plantilla no la activa solo' /
        'quien genera lote no lo aprueba solo' — the authorizer must be a
        distinct user."""
        policy = LoyaltyCardsAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(LoyaltyCardSegregationOfDutiesError):
            policy.authorize_exception(
                authorizer_user_id="disenador-1",
                requested_by="disenador-1",
                permission_code=LoyaltyCardsPermissions.TEMPLATE_ACTIVATE,
                operation_id="op-1",
                reason="motivo",
            )

    def test_hot_authorization_requires_authorizer_to_hold_permission(self):
        policy = LoyaltyCardsAuthorizationPolicy(DenyAllLoyaltyCardsPermissionCheckerForTests())
        with pytest.raises(LoyaltyCardPermissionDeniedError):
            policy.authorize_exception(
                authorizer_user_id="supervisor-1",
                requested_by="disenador-1",
                permission_code=LoyaltyCardsPermissions.TEMPLATE_ACTIVATE,
                operation_id="op-1",
                reason="motivo",
            )

    def test_grant_requires_reason(self):
        with pytest.raises(InvalidLoyaltyCardAuditFieldError):
            AuthorizationGrant(
                permission_code=LoyaltyCardsPermissions.BATCH_APPROVE,
                requested_by="disenador-1",
                authorized_by="supervisor-1",
                operation_id="op-1",
                reason="   ",
            )

    def test_grant_rejects_float_amount(self):
        with pytest.raises(InvalidLoyaltyCardAuditFieldError):
            AuthorizationGrant(
                permission_code=LoyaltyCardsPermissions.BATCH_APPROVE,
                requested_by="disenador-1",
                authorized_by="supervisor-1",
                operation_id="op-1",
                reason="motivo",
                amount=12.5,
            )


class TestCardAuditEntry:
    def test_valid_entry(self):
        entry = CardAuditEntry(
            user_id="operador-1",
            operation_id="op-1",
            action="CARD_REPRINTED",
            branch_id="branch-1",
        )
        assert entry.before == {}
        assert entry.occurred_at

    def test_requires_branch_id(self):
        with pytest.raises(InvalidLoyaltyCardAuditFieldError):
            CardAuditEntry(
                user_id="operador-1", operation_id="op-1", action="CARD_REPRINTED",
                branch_id="",
            )


def test_all_loyalty_cards_permissions_frozenset_matches_class_attrs():
    assert LoyaltyCardsPermissions.QR_ROTATE in ALL_LOYALTY_CARDS_PERMISSIONS
    assert LoyaltyCardsPermissions.REPRINT in ALL_LOYALTY_CARDS_PERMISSIONS
    assert LoyaltyCardsPermissions.BATCH_APPROVE in ALL_LOYALTY_CARDS_PERMISSIONS
