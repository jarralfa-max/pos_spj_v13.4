"""PRC-1 — seguridad de Pricing: permisos granulares, segregación, alcance, hot auth."""

import pytest

from backend.application.pricing.authorization import PricingAuthorizationPolicy
from backend.application.pricing.permissions import (
    ALL_PRICING_PERMISSIONS,
    PricingPermissions,
)
from backend.domain.pricing.exceptions import (
    BranchScopeError,
    PricingPermissionDeniedError,
    SegregationOfDutiesError,
)
from backend.domain.pricing.value_objects.authorization_grant import (
    PricingAuthorizationGrant,
)


class _Checker:
    def __init__(self, grants):
        self._grants = set(grants)

    def has_permission(self, user_id, code):
        return (user_id, code) in self._grants


class TestPermissionCatalog:
    def test_no_coarse_precios_permission(self):
        assert "PRECIOS" not in ALL_PRICING_PERMISSIONS
        assert all(c.startswith("PRICING_") for c in ALL_PRICING_PERMISSIONS)

    def test_key_codes_present(self):
        for c in (PricingPermissions.VIEW_COST, PricingPermissions.PRICE_MIN_OVERRIDE,
                  PricingPermissions.LIST_APPROVE, PricingPermissions.COST_MANAGE):
            assert c in ALL_PRICING_PERMISSIONS

    def test_unique_values(self):
        vals = [v for k, v in vars(PricingPermissions).items()
                if not k.startswith("_") and isinstance(v, str)]
        assert len(vals) == len(set(vals))


class TestGate:
    def test_require_ok(self):
        pol = PricingAuthorizationPolicy(_Checker({("u1", PricingPermissions.PRICE_EDIT)}))
        pol.require("u1", PricingPermissions.PRICE_EDIT)

    def test_require_denied(self):
        pol = PricingAuthorizationPolicy(_Checker(set()))
        with pytest.raises(PricingPermissionDeniedError):
            pol.require("u1", PricingPermissions.PRICE_EDIT)

    def test_unknown_permission(self):
        pol = PricingAuthorizationPolicy(_Checker(set()))
        with pytest.raises(PricingPermissionDeniedError):
            pol.require("u1", "PRICING_MADE_UP")

    def test_no_checker_allows_isolated(self):
        PricingAuthorizationPolicy().require("u1", PricingPermissions.PRICE_EDIT)

    def test_has_non_raising(self):
        pol = PricingAuthorizationPolicy(_Checker({("u1", PricingPermissions.VIEW_COST)}))
        assert pol.has("u1", PricingPermissions.VIEW_COST)
        assert not pol.has("u1", PricingPermissions.VIEW_MARGIN)


class TestSegregation:
    def test_creator_cannot_approve_own_list(self):
        pol = PricingAuthorizationPolicy()
        with pytest.raises(SegregationOfDutiesError):
            pol.ensure_segregation(actor_user_id="u1", creator_user_id="u1",
                                   approval_permission=PricingPermissions.LIST_APPROVE)

    def test_distinct_user_can_approve(self):
        PricingAuthorizationPolicy().ensure_segregation(
            actor_user_id="u2", creator_user_id="u1",
            approval_permission=PricingPermissions.LIST_ACTIVATE)

    def test_non_segregated_ignored(self):
        PricingAuthorizationPolicy().ensure_segregation(
            actor_user_id="u1", creator_user_id="u1",
            approval_permission=PricingPermissions.PRICE_EDIT)


class TestScope:
    def test_branch_in_scope(self):
        PricingAuthorizationPolicy().require_branch("u1", "b1", allowed_branches={"b1"})

    def test_branch_out_of_scope(self):
        with pytest.raises(BranchScopeError):
            PricingAuthorizationPolicy().require_branch("u1", "b3", allowed_branches={"b1"})

    def test_global_scope(self):
        PricingAuthorizationPolicy().require_branch("u1", "bX", allowed_branches=None)


class TestHotAuth:
    def test_grant_distinct_authorizer(self):
        pol = PricingAuthorizationPolicy(_Checker({("u1", PricingPermissions.PRICE_MIN_OVERRIDE)}))
        with pytest.raises(SegregationOfDutiesError):
            pol.authorize_exception(authorizer_user_id="u1", requested_by="u1",
                                    permission_code=PricingPermissions.PRICE_MIN_OVERRIDE,
                                    operation_id="op1", reason="cliente mayoreo")

    def test_grant_authorizer_needs_permission(self):
        pol = PricingAuthorizationPolicy(_Checker(set()))
        with pytest.raises(PricingPermissionDeniedError):
            pol.authorize_exception(authorizer_user_id="mgr", requested_by="u1",
                                    permission_code=PricingPermissions.PRICE_MIN_OVERRIDE,
                                    operation_id="op1", reason="cliente mayoreo")

    def test_valid_grant(self):
        pol = PricingAuthorizationPolicy(_Checker({("mgr", PricingPermissions.PRICE_MIN_OVERRIDE)}))
        g = pol.authorize_exception(authorizer_user_id="mgr", requested_by="u1",
                                    permission_code=PricingPermissions.PRICE_MIN_OVERRIDE,
                                    operation_id="op1", reason="venta bajo mínimo autorizada",
                                    entity_id="prod-1")
        assert isinstance(g, PricingAuthorizationGrant)
        assert g.authorized_by == "mgr" and g.entity_id == "prod-1"

    def test_grant_requires_reason(self):
        pol = PricingAuthorizationPolicy(_Checker({("mgr", PricingPermissions.PRICE_MIN_OVERRIDE)}))
        with pytest.raises(Exception):
            pol.authorize_exception(authorizer_user_id="mgr", requested_by="u1",
                                    permission_code=PricingPermissions.PRICE_MIN_OVERRIDE,
                                    operation_id="op1", reason="  ")
