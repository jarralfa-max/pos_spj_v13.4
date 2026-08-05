from decimal import Decimal

import pytest

from backend.application.losses.authorization import LossAuthorizationPolicy
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.exceptions import (
    LossConfigurationError,
    LossLimitExceededError,
    LossPermissionDeniedError,
    LossScopeError,
    LossSegregationOfDutiesError,
)


class Checker:
    def __init__(self, grants):
        self.grants = grants

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return permission_code in self.grants.get(user_id, set())


def _context(**changes):
    values = {
        "actor_user_id": "reporter",
        "active_branch_id": "branch-a",
        "assigned_branch_ids": frozenset({"branch-b"}),
        "allowed_warehouse_ids": frozenset({"warehouse-a"}),
        "permissions": frozenset({LossPermissions.REPORT}),
    }
    values.update(changes)
    return LossExecutionContext(**values)


def test_policy_is_fail_closed_without_checker():
    with pytest.raises(LossConfigurationError):
        LossAuthorizationPolicy().require("reporter", LossPermissions.REPORT)


def test_unknown_and_missing_permissions_are_denied():
    policy = LossAuthorizationPolicy(Checker({"reporter": {LossPermissions.REPORT}}))
    policy.require("reporter", LossPermissions.REPORT)
    with pytest.raises(LossPermissionDeniedError):
        policy.require("reporter", LossPermissions.APPROVE)
    with pytest.raises(LossPermissionDeniedError, match="desconocido"):
        policy.require("reporter", "MERMA.crear")


def test_context_enforces_branch_and_warehouse_scope():
    context = _context()
    context.enforce_branch("branch-a")
    context.enforce_branch("branch-b")
    context.enforce_warehouse("warehouse-a")
    with pytest.raises(LossScopeError):
        context.enforce_branch("branch-c")
    with pytest.raises(LossScopeError):
        context.enforce_warehouse("warehouse-b")


def test_global_scope_allows_any_branch_but_not_an_empty_target():
    context = _context(permissions=frozenset({LossPermissions.VIEW_ALL_BRANCHES}))
    context.enforce_branch("branch-z")
    context.enforce_warehouse("warehouse-z")
    with pytest.raises(LossScopeError):
        context.enforce_branch("")


def test_value_above_limit_requires_a_distinct_authorizer():
    grants = {
        "reporter": {LossPermissions.REPORT},
        "manager": {LossPermissions.APPROVE_OVER_LIMIT},
    }
    policy = LossAuthorizationPolicy(Checker(grants))
    context = _context()

    with pytest.raises(LossLimitExceededError):
        policy.authorize_value(
            context=context, permission_code=LossPermissions.REPORT,
            operation_id="operation-1", value_reference=Decimal("501.00"),
            approval_limit=Decimal("500.00"), reason="Caducidad",
        )

    grant = policy.authorize_value(
        context=context, permission_code=LossPermissions.REPORT,
        operation_id="operation-1", value_reference=Decimal("501.00"),
        approval_limit=Decimal("500.00"), reason="Caducidad",
        authorizer_user_id="manager",
    )
    assert grant is not None
    assert grant.requested_by == "reporter"
    assert grant.authorized_by == "manager"
    assert grant.value_reference == Decimal("501.00")


def test_requester_cannot_authorize_own_over_limit_loss():
    grants = {"reporter": {LossPermissions.REPORT, LossPermissions.APPROVE_OVER_LIMIT}}
    policy = LossAuthorizationPolicy(Checker(grants))
    with pytest.raises(LossSegregationOfDutiesError):
        policy.authorize_value(
            context=_context(), permission_code=LossPermissions.REPORT,
            operation_id="operation-2", value_reference=Decimal("501"),
            approval_limit=Decimal("500"), reason="Daño",
            authorizer_user_id="reporter",
        )


def test_security_values_reject_float():
    policy = LossAuthorizationPolicy(Checker({"reporter": {LossPermissions.REPORT}}))
    with pytest.raises(TypeError, match="Decimal"):
        policy.authorize_value(
            context=_context(), permission_code=LossPermissions.REPORT,
            operation_id="operation-3", value_reference=501.0,
            approval_limit=Decimal("500"), reason="Daño",
        )
