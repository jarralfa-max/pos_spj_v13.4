"""P0-A slice 3 (§5.3/§5.4) — trusted execution context + fail-closed resolver.

The context carries the authenticated actor and resolved scope and validates targets
via InventoryScopePolicy; the resolver never fabricates identity — it raises the
canonical configuration errors instead.
"""

import pytest

from backend.application.inventory.composition import InventoryUseCaseFactory
from backend.application.inventory.execution_context import (
    InventoryExecutionContext,
    resolve_inventory_execution_context,
)
from backend.application.inventory.permissions import InventoryPermissions
from backend.domain.inventory.exceptions import (
    BranchConfigurationRequiredError,
    BranchScopeError,
    InventoryAuthenticationRequiredError,
    WarehouseConfigurationRequiredError,
    WarehouseScopeError,
)


class _Session:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ── resolver fail-closed (§5.4) ──────────────────────────────────────────────
def test_resolver_denies_without_session():
    with pytest.raises(InventoryAuthenticationRequiredError):
        resolve_inventory_execution_context(None)


def test_resolver_denies_without_user():
    with pytest.raises(InventoryAuthenticationRequiredError):
        resolve_inventory_execution_context(_Session(user_id=""))


def test_resolver_requires_active_branch():
    with pytest.raises(BranchConfigurationRequiredError):
        resolve_inventory_execution_context(_Session(user_id="u1", branch_id=""))


def test_resolver_builds_context_from_session():
    ctx = resolve_inventory_execution_context(_Session(
        user_id="u1", active_branch_id="b1",
        assigned_branch_ids=["b1", "b2"],
        allowed_warehouse_ids=["w1"],
        permissions=[InventoryPermissions.VIEW_ASSIGNED_BRANCHES],
        device_id="dev-9"))
    assert ctx.actor_user_id == "u1" and ctx.active_branch_id == "b1"
    assert ctx.assigned_branch_ids == frozenset({"b1", "b2"})
    assert ctx.allowed_warehouse_ids == frozenset({"w1"})
    assert ctx.device_id == "dev-9"


# ── scope enforcement (§5.3) ─────────────────────────────────────────────────
def _ctx(**kw):
    base = dict(actor_user_id="u1", active_branch_id="b1",
                permissions=frozenset({InventoryPermissions.VIEW_OWN_BRANCH}))
    base.update(kw)
    return InventoryExecutionContext(**base)


def test_enforce_branch_allows_own_and_denies_other():
    ctx = _ctx()
    ctx.enforce_branch("b1")
    with pytest.raises(BranchScopeError):
        ctx.enforce_branch("b9")


def test_enforce_warehouse_denies_out_of_scope_and_empty():
    ctx = _ctx(allowed_warehouse_ids=frozenset({"w1"}))
    ctx.enforce_warehouse("w1")
    with pytest.raises(WarehouseScopeError):
        ctx.enforce_warehouse("w9")
    with pytest.raises(WarehouseConfigurationRequiredError):
        ctx.enforce_warehouse("")


def test_enforce_warehouse_all_warehouses_bypass():
    ctx = _ctx()
    ctx.enforce_warehouse("w9", has_all_warehouses=True)


# ── factory integration ──────────────────────────────────────────────────────
def test_factory_execution_context_fails_closed_without_session():
    factory = InventoryUseCaseFactory.for_tests()  # no session_context
    with pytest.raises(InventoryAuthenticationRequiredError):
        factory.execution_context()


def test_factory_execution_context_from_session():
    factory = InventoryUseCaseFactory.from_session(
        _Session(user_id="u1", branch_id="b1"))
    ctx = factory.execution_context()
    assert ctx.actor_user_id == "u1" and ctx.active_branch_id == "b1"
