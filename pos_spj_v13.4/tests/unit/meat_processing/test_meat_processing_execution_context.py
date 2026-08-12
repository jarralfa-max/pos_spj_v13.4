import pytest

from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.domain.meat_processing.exceptions import (
    MeatProcessingConfigurationError,
    MeatProcessingScopeError,
)


def test_requires_actor_and_active_branch():
    with pytest.raises(MeatProcessingConfigurationError):
        MeatProcessingExecutionContext(actor_user_id="", active_branch_id="branch-1")
    with pytest.raises(MeatProcessingConfigurationError):
        MeatProcessingExecutionContext(actor_user_id="user-1", active_branch_id="")


def test_enforce_branch_allows_active_and_assigned_branches():
    context = MeatProcessingExecutionContext(
        actor_user_id="user-1", active_branch_id="branch-1",
        assigned_branch_ids=frozenset({"branch-2"}))
    context.enforce_branch("branch-1")
    context.enforce_branch("branch-2")
    with pytest.raises(MeatProcessingScopeError):
        context.enforce_branch("branch-3")
    with pytest.raises(MeatProcessingScopeError):
        context.enforce_branch("")


def test_global_scope_permission_bypasses_branch_and_warehouse_enforcement():
    context = MeatProcessingExecutionContext(
        actor_user_id="user-1", active_branch_id="branch-1",
        permissions=frozenset({MeatProcessingPermissions.VIEW_ALL_BRANCHES}))
    context.enforce_branch("any-other-branch")
    context.enforce_warehouse("any-other-warehouse")


def test_enforce_warehouse_requires_allowed_list_without_global_scope():
    context = MeatProcessingExecutionContext(
        actor_user_id="user-1", active_branch_id="branch-1",
        allowed_warehouse_ids=frozenset({"wh-1"}))
    context.enforce_warehouse("wh-1")
    with pytest.raises(MeatProcessingScopeError):
        context.enforce_warehouse("wh-2")
