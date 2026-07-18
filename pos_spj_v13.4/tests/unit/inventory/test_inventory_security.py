"""INV-1 — inventory security domain/application tests.

Covers granular permissions, the authorization gate + hot authorization,
configurable limits (WITHIN/REQUIRES_APPROVAL/EXCEEDS), segregation of duties,
and branch/warehouse scope. Pure domain — no DB.
"""

from decimal import Decimal

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import (
    ALL_INVENTORY_PERMISSIONS,
    InventoryPermissions,
)
from backend.domain.inventory.enums import LimitDecision
from backend.domain.inventory.exceptions import (
    BranchScopeError,
    InvalidInventoryLimitError,
    InventoryAuthorizationRequiredError,
    InventoryLimitExceededError,
    InventoryPermissionDeniedError,
    SegregationOfDutiesError,
    WarehouseScopeError,
)
from backend.domain.inventory.policies import (
    InventoryLimitPolicy,
    InventoryScopePolicy,
    SegregationOfDutiesPolicy,
)
from backend.domain.inventory.value_objects import (
    AuthorizationGrant,
    InventoryOperationLimit,
)


def _limit(cap="100", approval="20"):
    return InventoryOperationLimit(
        approval_threshold=Decimal(approval), hard_cap=Decimal(cap))


# ── permisos granulares ────────────────────────────────────────────────────
class TestPermissions:
    def test_catalog_is_granular_not_broad(self):
        assert "INVENTORY_ALL" not in ALL_INVENTORY_PERMISSIONS
        assert "INVENTARIO" not in ALL_INVENTORY_PERMISSIONS
        assert len(ALL_INVENTORY_PERMISSIONS) >= 60

    def test_all_codes_are_prefixed_strings(self):
        for code in ALL_INVENTORY_PERMISSIONS:
            assert isinstance(code, str) and code.startswith("INVENTORY_")

    def test_no_duplicate_codes(self):
        values = [v for k, v in vars(InventoryPermissions).items()
                  if not k.startswith("_") and isinstance(v, str)]
        assert len(values) == len(set(values))

    def test_key_sensitive_actions_present(self):
        for code in (InventoryPermissions.MOVEMENT_REVERSE,
                     InventoryPermissions.TRANSFER_APPROVE,
                     InventoryPermissions.TRANSFER_DISPATCH,
                     InventoryPermissions.TRANSFER_RECEIVE,
                     InventoryPermissions.COUNT_CONFIRM,
                     InventoryPermissions.COUNT_VIEW_EXPECTED,
                     InventoryPermissions.ADJUSTMENT_APPROVE,
                     InventoryPermissions.QUALITY_RELEASE,
                     InventoryPermissions.WEIGHT_MANUAL_OVERRIDE,
                     InventoryPermissions.NEGATIVE_OVERRIDE):
            assert code in ALL_INVENTORY_PERMISSIONS


# ── autorización + hot authorization ───────────────────────────────────────
class TestAuthorization:
    def test_unknown_permission(self):
        with pytest.raises(InventoryPermissionDeniedError):
            InventoryAuthorizationPolicy().require("u1", "INVENTORY_NOPE")

    def test_no_checker_allows_known(self):
        InventoryAuthorizationPolicy().require("u1", InventoryPermissions.MOVEMENT_CREATE)

    def test_checker_denies(self):
        class Deny:
            def has_permission(self, u, p):
                return False
        with pytest.raises(InventoryPermissionDeniedError):
            InventoryAuthorizationPolicy(Deny()).require(
                "u1", InventoryPermissions.MOVEMENT_CREATE)

    def test_checker_requires_user(self):
        class Allow:
            def has_permission(self, u, p):
                return True
        with pytest.raises(InventoryPermissionDeniedError):
            InventoryAuthorizationPolicy(Allow()).require(
                "", InventoryPermissions.MOVEMENT_CREATE)

    def test_hot_authorization_returns_audit_grant(self):
        grant = InventoryAuthorizationPolicy().authorize_exception(
            authorizer_user_id="boss", requested_by="clerk",
            permission_code=InventoryPermissions.ADJUSTMENT_APPROVE,
            operation_id="op-1", reason="conteo crítico", quantity=Decimal("5"))
        assert isinstance(grant, AuthorizationGrant)
        assert grant.authorized_by == "boss" and grant.requested_by == "clerk"
        assert grant.quantity == Decimal("5")

    def test_hot_authorization_requires_authorizer(self):
        with pytest.raises(InventoryPermissionDeniedError):
            InventoryAuthorizationPolicy().authorize_exception(
                authorizer_user_id="", requested_by="clerk",
                permission_code=InventoryPermissions.ADJUSTMENT_APPROVE,
                operation_id="op", reason="x")

    def test_hot_authorization_rejects_self_authorization(self):
        with pytest.raises(SegregationOfDutiesError):
            InventoryAuthorizationPolicy().authorize_exception(
                authorizer_user_id="u1", requested_by="u1",
                permission_code=InventoryPermissions.ADJUSTMENT_APPROVE,
                operation_id="op", reason="x")

    def test_grant_requires_reason(self):
        with pytest.raises(InvalidInventoryLimitError):
            AuthorizationGrant(
                permission_code="INVENTORY_ADJUSTMENT_APPROVE", requested_by="a",
                authorized_by="b", operation_id="op", reason="  ")

    def test_grant_rejects_float(self):
        with pytest.raises(InvalidInventoryLimitError):
            AuthorizationGrant(
                permission_code="INVENTORY_ADJUSTMENT_APPROVE", requested_by="a",
                authorized_by="b", operation_id="op", reason="ok", quantity=5.0)


# ── límites ────────────────────────────────────────────────────────────────
class TestLimits:
    def test_within(self):
        assert InventoryLimitPolicy().classify(Decimal("10"), _limit()) \
            is LimitDecision.WITHIN

    def test_requires_approval(self):
        assert InventoryLimitPolicy().classify(Decimal("50"), _limit()) \
            is LimitDecision.REQUIRES_APPROVAL

    def test_exceeds(self):
        assert InventoryLimitPolicy().classify(Decimal("500"), _limit()) \
            is LimitDecision.EXCEEDS

    def test_no_limit_is_within(self):
        assert InventoryLimitPolicy().classify(Decimal("9999"), None) \
            is LimitDecision.WITHIN

    def test_negative_variance_uses_magnitude(self):
        assert InventoryLimitPolicy().classify(Decimal("-500"), _limit()) \
            is LimitDecision.EXCEEDS

    def test_enforce_direct_raises(self):
        pol = InventoryLimitPolicy()
        with pytest.raises(InventoryAuthorizationRequiredError):
            pol.enforce_direct_execution(Decimal("50"), _limit())
        with pytest.raises(InventoryLimitExceededError):
            pol.enforce_direct_execution(Decimal("500"), _limit())

    def test_limit_rejects_float(self):
        with pytest.raises(InvalidInventoryLimitError):
            InventoryOperationLimit(hard_cap=100.0)

    def test_cap_below_approval_invalid(self):
        with pytest.raises(InvalidInventoryLimitError):
            InventoryOperationLimit(approval_threshold=Decimal("50"),
                                    hard_cap=Decimal("10"))


# ── segregación de funciones (§47) ─────────────────────────────────────────
class TestSegregation:
    def setup_method(self):
        self.pol = SegregationOfDutiesPolicy()

    def test_counter_cannot_self_approve_critical(self):
        with pytest.raises(SegregationOfDutiesError):
            self.pol.enforce_counter_not_self_approving_critical(
                "u1", "u1", is_critical=True)

    def test_counter_self_ok_when_not_critical(self):
        self.pol.enforce_counter_not_self_approving_critical(
            "u1", "u1", is_critical=False)

    def test_dispatcher_not_receiver(self):
        with pytest.raises(SegregationOfDutiesError):
            self.pol.enforce_dispatcher_not_receiver("u1", "u1")
        self.pol.enforce_dispatcher_not_receiver("u1", "u2")

    def test_adjustment_creator_not_self_approving(self):
        with pytest.raises(SegregationOfDutiesError):
            self.pol.enforce_adjustment_creator_not_self_approving(
                "u1", "u1", requires_approval=True)
        self.pol.enforce_adjustment_creator_not_self_approving(
            "u1", "u1", requires_approval=False)

    def test_quality_blocker_not_releaser(self):
        with pytest.raises(SegregationOfDutiesError):
            self.pol.enforce_quality_blocker_not_releaser(
                "u1", "u1", self_release_forbidden=True)
        self.pol.enforce_quality_blocker_not_releaser(
            "u1", "u1", self_release_forbidden=False)

    def test_transfer_modification_needs_justification(self):
        with pytest.raises(SegregationOfDutiesError):
            self.pol.enforce_transfer_modification_justified("   ")
        self.pol.enforce_transfer_modification_justified("corrige cantidad")

    def test_manual_weight_out_of_tolerance_needs_distinct_authorizer(self):
        with pytest.raises(SegregationOfDutiesError):
            self.pol.enforce_manual_weight_authorized(
                "u1", "u1", within_tolerance=False)
        with pytest.raises(SegregationOfDutiesError):
            self.pol.enforce_manual_weight_authorized(
                "u1", "", within_tolerance=False)
        self.pol.enforce_manual_weight_authorized("u1", "u2", within_tolerance=False)
        self.pol.enforce_manual_weight_authorized("u1", "u1", within_tolerance=True)


# ── alcance sucursal / almacén ─────────────────────────────────────────────
class TestScope:
    def setup_method(self):
        self.pol = InventoryScopePolicy()

    def test_all_branches(self):
        self.pol.enforce_branch_access(
            user_permissions={InventoryPermissions.VIEW_ALL_BRANCHES},
            user_branch_id="b1", assigned_branch_ids=set(), target_branch_id="b9")

    def test_assigned_branch(self):
        self.pol.enforce_branch_access(
            user_permissions={InventoryPermissions.VIEW_ASSIGNED_BRANCHES},
            user_branch_id="b1", assigned_branch_ids={"b2", "b3"}, target_branch_id="b2")
        with pytest.raises(BranchScopeError):
            self.pol.enforce_branch_access(
                user_permissions={InventoryPermissions.VIEW_ASSIGNED_BRANCHES},
                user_branch_id="b1", assigned_branch_ids={"b2"}, target_branch_id="b9")

    def test_own_branch_only(self):
        self.pol.enforce_branch_access(
            user_permissions={InventoryPermissions.VIEW_OWN_BRANCH},
            user_branch_id="b1", assigned_branch_ids=set(), target_branch_id="b1")
        with pytest.raises(BranchScopeError):
            self.pol.enforce_branch_access(
                user_permissions={InventoryPermissions.VIEW_OWN_BRANCH},
                user_branch_id="b1", assigned_branch_ids=set(), target_branch_id="b2")

    def test_no_scope_permission_denies(self):
        with pytest.raises(BranchScopeError):
            self.pol.enforce_branch_access(
                user_permissions=set(), user_branch_id="b1",
                assigned_branch_ids=set(), target_branch_id="b1")

    def test_warehouse_scope(self):
        self.pol.enforce_warehouse_access(
            allowed_warehouse_ids={"w1"}, target_warehouse_id="w1")
        self.pol.enforce_warehouse_access(
            allowed_warehouse_ids=set(), target_warehouse_id="w9",
            has_all_warehouses=True)
        with pytest.raises(WarehouseScopeError):
            self.pol.enforce_warehouse_access(
                allowed_warehouse_ids={"w1"}, target_warehouse_id="w9")
