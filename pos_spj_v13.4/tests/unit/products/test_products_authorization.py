"""PROD-1 — seguridad de Productos: permisos granulares, segregación, alcance, hot auth."""

import pytest

from backend.application.products.authorization import ProductsAuthorizationPolicy
from backend.application.products.permissions import (
    ALL_PRODUCT_PERMISSIONS,
    ProductPermissions,
)
from backend.domain.products.exceptions import (
    BranchScopeError,
    ProductPermissionDeniedError,
    SegregationOfDutiesError,
)
from backend.domain.products.value_objects.authorization_grant import (
    ProductAuthorizationGrant,
)
from backend.domain.products.value_objects.product_audit_entry import ProductAuditEntry


class _Checker:
    def __init__(self, grants):
        self._grants = {(u, p) for u, p in grants}

    def has_permission(self, user_id, permission_code):
        return (user_id, permission_code) in self._grants


# ── permisos granulares ──────────────────────────────────────────────────────
class TestPermissionCatalog:
    def test_no_coarse_productos_permission(self):
        # §38: nunca un único permiso PRODUCTOS
        assert "PRODUCTOS" not in ALL_PRODUCT_PERMISSIONS
        assert "PRODUCTO" not in ALL_PRODUCT_PERMISSIONS

    def test_all_codes_are_prefixed_and_unique(self):
        assert all(c.startswith("PRODUCTS_") for c in ALL_PRODUCT_PERMISSIONS)
        # sin colisiones de valor
        values = [v for k, v in vars(ProductPermissions).items()
                  if not k.startswith("_") and isinstance(v, str)]
        assert len(values) == len(set(values))

    def test_key_granular_codes_present(self):
        for code in (
            ProductPermissions.RECIPE_APPROVE,
            ProductPermissions.YIELD_ACTIVATE,
            ProductPermissions.MEAT_CLASSIFICATION_MANAGE,
            ProductPermissions.INTERNAL_CREATE,
            ProductPermissions.EXTERNAL_APPROVE,
        ):
            assert code in ALL_PRODUCT_PERMISSIONS


# ── el backend revalida (§37) ────────────────────────────────────────────────
class TestPermissionGate:
    def test_require_passes_with_permission(self):
        pol = ProductsAuthorizationPolicy(_Checker({("u1", ProductPermissions.CREATE)}))
        pol.require("u1", ProductPermissions.CREATE)  # no raise

    def test_require_denies_without_permission(self):
        pol = ProductsAuthorizationPolicy(_Checker(set()))
        with pytest.raises(ProductPermissionDeniedError):
            pol.require("u1", ProductPermissions.CREATE)

    def test_require_unknown_permission_denied(self):
        pol = ProductsAuthorizationPolicy(_Checker({("u1", "PRODUCTS_CREATE")}))
        with pytest.raises(ProductPermissionDeniedError):
            pol.require("u1", "PRODUCTS_MADE_UP")

    def test_require_no_user_denied(self):
        pol = ProductsAuthorizationPolicy(_Checker(set()))
        with pytest.raises(ProductPermissionDeniedError):
            pol.require("", ProductPermissions.CREATE)

    def test_no_checker_allows_isolated_tests(self):
        pol = ProductsAuthorizationPolicy()
        pol.require("u1", ProductPermissions.CREATE)  # no raise

    def test_has_is_non_raising(self):
        pol = ProductsAuthorizationPolicy(_Checker({("u1", ProductPermissions.VIEW_COST_REFERENCE)}))
        assert pol.has("u1", ProductPermissions.VIEW_COST_REFERENCE) is True
        assert pol.has("u1", ProductPermissions.VIEW_INTERNAL) is False
        assert pol.has("u1", "PRODUCTS_MADE_UP") is False


# ── segregación de funciones (§39) ───────────────────────────────────────────
class TestSegregationOfDuties:
    def test_creator_cannot_approve_own_recipe(self):
        pol = ProductsAuthorizationPolicy()
        with pytest.raises(SegregationOfDutiesError):
            pol.ensure_segregation(
                actor_user_id="u1", creator_user_id="u1",
                approval_permission=ProductPermissions.RECIPE_APPROVE)

    def test_distinct_user_can_approve(self):
        pol = ProductsAuthorizationPolicy()
        pol.ensure_segregation(
            actor_user_id="u2", creator_user_id="u1",
            approval_permission=ProductPermissions.RECIPE_ACTIVATE)  # no raise

    def test_non_segregated_permission_is_ignored(self):
        pol = ProductsAuthorizationPolicy()
        # editar no es un par crea→aprueba: mismo usuario permitido
        pol.ensure_segregation(
            actor_user_id="u1", creator_user_id="u1",
            approval_permission=ProductPermissions.EDIT)  # no raise

    def test_import_creator_cannot_self_approve(self):
        pol = ProductsAuthorizationPolicy()
        with pytest.raises(SegregationOfDutiesError):
            pol.ensure_segregation(
                actor_user_id="u9", creator_user_id="u9",
                approval_permission=ProductPermissions.IMPORT_APPROVE)


# ── alcance (§37) ────────────────────────────────────────────────────────────
class TestScope:
    def test_branch_in_scope_passes(self):
        pol = ProductsAuthorizationPolicy()
        pol.require_branch("u1", "b1", allowed_branches={"b1", "b2"})  # no raise

    def test_branch_out_of_scope_denied(self):
        pol = ProductsAuthorizationPolicy()
        with pytest.raises(BranchScopeError):
            pol.require_branch("u1", "b3", allowed_branches={"b1", "b2"})

    def test_global_scope_allows_any_branch(self):
        pol = ProductsAuthorizationPolicy()
        pol.require_branch("u1", "b9", allowed_branches=None)  # no raise

    def test_internal_visibility_requires_permission(self):
        pol = ProductsAuthorizationPolicy(_Checker({("u1", ProductPermissions.VIEW_MEAT)}))
        with pytest.raises(ProductPermissionDeniedError):
            pol.require_product_type_visibility("u1", internal_only=True)

    def test_meat_visibility_requires_permission(self):
        pol = ProductsAuthorizationPolicy(_Checker({("u1", ProductPermissions.VIEW_INTERNAL)}))
        with pytest.raises(ProductPermissionDeniedError):
            pol.require_product_type_visibility("u1", is_meat=True)

    def test_visibility_passes_with_both(self):
        pol = ProductsAuthorizationPolicy(_Checker({
            ("u1", ProductPermissions.VIEW_INTERNAL),
            ("u1", ProductPermissions.VIEW_MEAT),
        }))
        pol.require_product_type_visibility("u1", internal_only=True, is_meat=True)


# ── autorización en caliente (§48) ───────────────────────────────────────────
class TestHotAuthorization:
    def test_grant_requires_distinct_authorizer(self):
        pol = ProductsAuthorizationPolicy(_Checker({("u1", ProductPermissions.ACTIVATE)}))
        with pytest.raises(SegregationOfDutiesError):
            pol.authorize_exception(
                authorizer_user_id="u1", requested_by="u1",
                permission_code=ProductPermissions.ACTIVATE,
                operation_id="op1", reason="alta urgente")

    def test_grant_authorizer_needs_permission(self):
        pol = ProductsAuthorizationPolicy(_Checker(set()))
        with pytest.raises(ProductPermissionDeniedError):
            pol.authorize_exception(
                authorizer_user_id="mgr", requested_by="u1",
                permission_code=ProductPermissions.ACTIVATE,
                operation_id="op1", reason="alta urgente")

    def test_valid_grant_returns_audit_record(self):
        pol = ProductsAuthorizationPolicy(_Checker({("mgr", ProductPermissions.ACTIVATE)}))
        grant = pol.authorize_exception(
            authorizer_user_id="mgr", requested_by="u1",
            permission_code=ProductPermissions.ACTIVATE,
            operation_id="op1", reason="alta urgente", entity_id="prod-1")
        assert isinstance(grant, ProductAuthorizationGrant)
        assert grant.authorized_by == "mgr" and grant.requested_by == "u1"
        assert grant.entity_id == "prod-1"

    def test_grant_requires_reason(self):
        pol = ProductsAuthorizationPolicy(_Checker({("mgr", ProductPermissions.ACTIVATE)}))
        with pytest.raises(Exception):
            pol.authorize_exception(
                authorizer_user_id="mgr", requested_by="u1",
                permission_code=ProductPermissions.ACTIVATE,
                operation_id="op1", reason="  ")


# ── auditoría (§40) ──────────────────────────────────────────────────────────
class TestAuditEntry:
    def test_audit_entry_has_uuid_and_timestamp(self):
        e = ProductAuditEntry(
            action="PRODUCT_APPROVED", entity_id="prod-1", user_id="u2",
            operation_id="op1", authorized_by="mgr", reason="ok",
            before={"status": "UNDER_REVIEW"}, after={"status": "ACTIVE"})
        assert len(e.id) >= 32 and e.occurred_at
        assert e.before != e.after

    def test_audit_entry_requires_core_fields(self):
        with pytest.raises(Exception):
            ProductAuditEntry(action="", entity_id="p", user_id="u", operation_id="op")
        with pytest.raises(Exception):
            ProductAuditEntry(action="X", entity_id="", user_id="u", operation_id="op")
