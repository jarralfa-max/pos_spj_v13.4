"""ORD-1 — Pedidos/Delivery permission gate, hot authorization and audit
value objects. Mirrors tests/unit/test_loyalty_security.py's structure (same
PermissionChecker/AuthorizationPolicy/AuthorizationGrant contract)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import (
    AllowAllOrdersDeliveryPermissionCheckerForTests,
    DenyAllOrdersDeliveryPermissionCheckerForTests,
    OrdersDeliveryAuthorizationPolicy,
)
from backend.application.orders_delivery.permissions import (
    ALL_ORDERS_DELIVERY_PERMISSIONS,
    OrdersDeliveryPermissions,
)
from backend.domain.orders_delivery.exceptions import (
    InvalidOrdersDeliveryAuditFieldError,
    OrdersDeliveryConfigurationError,
    OrdersDeliveryPermissionDeniedError,
    OrdersDeliverySegregationOfDutiesError,
)
from backend.domain.orders_delivery.value_objects.authorization_grant import AuthorizationGrant
from backend.domain.orders_delivery.value_objects.orders_delivery_audit_entry import (
    OrdersDeliveryAuditEntry,
)


class TestOrdersDeliveryAuthorizationPolicy:
    def test_unknown_permission_rejected(self):
        policy = OrdersDeliveryAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(OrdersDeliveryPermissionDeniedError):
            policy.require("u1", "DELIVERY.no_existe")

    def test_no_checker_is_fail_closed(self):
        policy = OrdersDeliveryAuthorizationPolicy()
        with pytest.raises(OrdersDeliveryConfigurationError):
            policy.require("u1", OrdersDeliveryPermissions.WEIGHT_OVERRIDE)

    def test_permissive_for_tests_allows_known_code(self):
        policy = OrdersDeliveryAuthorizationPolicy.permissive_for_tests()
        policy.require("u1", OrdersDeliveryPermissions.WEIGHT_OVERRIDE)  # does not raise

    def test_deny_all_checker_denies(self):
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        with pytest.raises(OrdersDeliveryPermissionDeniedError):
            policy.require("u1", OrdersDeliveryPermissions.WEIGHT_OVERRIDE)

    def test_has_permission_probe_is_fail_closed_without_checker(self):
        policy = OrdersDeliveryAuthorizationPolicy()
        assert policy.has_permission("u1", OrdersDeliveryPermissions.WEIGHT_OVERRIDE) is False

    def test_has_permission_probe_requires_user_id(self):
        policy = OrdersDeliveryAuthorizationPolicy(AllowAllOrdersDeliveryPermissionCheckerForTests())
        assert policy.has_permission("", OrdersDeliveryPermissions.WEIGHT_OVERRIDE) is False

    def test_require_requires_authenticated_user(self):
        policy = OrdersDeliveryAuthorizationPolicy(AllowAllOrdersDeliveryPermissionCheckerForTests())
        with pytest.raises(OrdersDeliveryPermissionDeniedError):
            policy.require("", OrdersDeliveryPermissions.WEIGHT_OVERRIDE)


class TestOrdersDeliveryHotAuthorization:
    def test_hot_authorization_returns_audit_grant(self):
        grant = OrdersDeliveryAuthorizationPolicy.permissive_for_tests().authorize_exception(
            authorizer_user_id="supervisor-1",
            requested_by="preparador-1",
            permission_code=OrdersDeliveryPermissions.WEIGHT_OVERRIDE,
            operation_id="op-1",
            reason="Ajuste de peso fuera de tolerancia",
            weight=Decimal("2.180"),
            order_id="order-1",
        )
        assert isinstance(grant, AuthorizationGrant)
        assert grant.authorized_by == "supervisor-1"
        assert grant.requested_by == "preparador-1"
        assert grant.weight == Decimal("2.180")
        assert grant.order_id == "order-1"

    def test_hot_authorization_requires_authorizer(self):
        policy = OrdersDeliveryAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(OrdersDeliveryPermissionDeniedError):
            policy.authorize_exception(
                authorizer_user_id="",
                requested_by="preparador-1",
                permission_code=OrdersDeliveryPermissions.WEIGHT_OVERRIDE,
                operation_id="op-1",
                reason="motivo",
            )

    def test_hot_authorization_rejects_self_authorization(self):
        """Master prompt §64: 'quien asigna repartidor no debe liquidar
        efectivo' — the authorizer must be a distinct user."""
        policy = OrdersDeliveryAuthorizationPolicy.permissive_for_tests()
        with pytest.raises(OrdersDeliverySegregationOfDutiesError):
            policy.authorize_exception(
                authorizer_user_id="preparador-1",
                requested_by="preparador-1",
                permission_code=OrdersDeliveryPermissions.WEIGHT_OVERRIDE,
                operation_id="op-1",
                reason="motivo",
            )

    def test_hot_authorization_requires_authorizer_to_hold_permission(self):
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        with pytest.raises(OrdersDeliveryPermissionDeniedError):
            policy.authorize_exception(
                authorizer_user_id="supervisor-1",
                requested_by="preparador-1",
                permission_code=OrdersDeliveryPermissions.WEIGHT_OVERRIDE,
                operation_id="op-1",
                reason="motivo",
            )

    def test_grant_requires_reason(self):
        with pytest.raises(InvalidOrdersDeliveryAuditFieldError):
            AuthorizationGrant(
                permission_code=OrdersDeliveryPermissions.DELIVERY_REVERSE,
                requested_by="operador-1",
                authorized_by="supervisor-1",
                operation_id="op-1",
                reason="   ",
            )

    def test_grant_rejects_float_amount(self):
        with pytest.raises(InvalidOrdersDeliveryAuditFieldError):
            AuthorizationGrant(
                permission_code=OrdersDeliveryPermissions.DELIVERY_REVERSE,
                requested_by="operador-1",
                authorized_by="supervisor-1",
                operation_id="op-1",
                reason="motivo",
                amount=12.5,
            )

    def test_grant_rejects_float_weight(self):
        with pytest.raises(InvalidOrdersDeliveryAuditFieldError):
            AuthorizationGrant(
                permission_code=OrdersDeliveryPermissions.WEIGHT_OVERRIDE,
                requested_by="operador-1",
                authorized_by="supervisor-1",
                operation_id="op-1",
                reason="motivo",
                weight=2.18,
            )


class TestOrdersDeliveryAuditEntry:
    def test_valid_entry(self):
        entry = OrdersDeliveryAuditEntry(
            user_id="operador-1",
            operation_id="op-1",
            action="ORDER_CONFIRMED",
            branch_id="branch-1",
        )
        assert entry.before == {}
        assert entry.after == {}
        assert entry.occurred_at

    def test_requires_branch_id(self):
        with pytest.raises(InvalidOrdersDeliveryAuditFieldError):
            OrdersDeliveryAuditEntry(
                user_id="operador-1", operation_id="op-1", action="ORDER_CONFIRMED",
                branch_id="",
            )

    def test_requires_action(self):
        with pytest.raises(InvalidOrdersDeliveryAuditFieldError):
            OrdersDeliveryAuditEntry(
                user_id="operador-1", operation_id="op-1", action="",
                branch_id="branch-1",
            )


def test_all_orders_delivery_permissions_frozenset_matches_class_attrs():
    assert OrdersDeliveryPermissions.WEIGHT_OVERRIDE in ALL_ORDERS_DELIVERY_PERMISSIONS
    assert OrdersDeliveryPermissions.DELIVERY_REVERSE in ALL_ORDERS_DELIVERY_PERMISSIONS
    assert OrdersDeliveryPermissions.SETTLEMENT_APPROVE in ALL_ORDERS_DELIVERY_PERMISSIONS
