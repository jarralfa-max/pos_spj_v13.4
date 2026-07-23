"""PROD-2 — Product Master: entidad Product, VOs, tipos/estados/roles, policies."""

import pytest

from backend.domain.products.entities.product import Product
from backend.domain.products.enums import (
    LifecycleStatus,
    ProductRole,
    ProductType,
)
from backend.domain.products.events import ALL_PRODUCT_EVENTS, ProductEvents
from backend.domain.products.exceptions import (
    InvalidProductStateError,
    InvalidProductTypeError,
    ProductIncompleteError,
    ProductsDomainError,
    SpeciesRequiredError,
)
from backend.domain.products.policies.product_creation_policy import validate_creation
from backend.domain.products.policies.product_lifecycle_policy import (
    allowed_targets,
    can_transition,
)
from backend.domain.products.value_objects.product_code import ProductCode
from backend.domain.products.value_objects.product_name import ProductName


def _product(**kw):
    base = dict(code="ABR-001", name="Refresco Cola 600ml",
                product_type=ProductType.RESALE_PRODUCT, base_unit_id="u-pza",
                category_id="cat-1")
    base.update(kw)
    return Product(**base)


# ── value objects ────────────────────────────────────────────────────────────
class TestValueObjects:
    def test_product_code_normalizes_upper(self):
        assert ProductCode(" abr-001 ").value == "ABR-001"

    def test_product_code_rejects_empty_and_bad_chars(self):
        with pytest.raises(ProductsDomainError):
            ProductCode("  ")
        with pytest.raises(ProductsDomainError):
            ProductCode("has space")

    def test_product_name_normalized_search_form(self):
        n = ProductName("Arráchera Añejo")
        assert n.value == "Arráchera Añejo"
        assert n.normalized == "arrachera anejo"

    def test_product_name_too_short(self):
        with pytest.raises(ProductsDomainError):
            ProductName("x")


# ── identidad e invariantes ──────────────────────────────────────────────────
class TestProductIdentity:
    def test_id_is_uuidv7_string(self):
        p = _product()
        assert isinstance(p.id, str) and len(p.id) >= 32
        assert p.id.count("-") == 4  # canonical uuid form

    def test_requires_base_unit(self):
        with pytest.raises(ProductsDomainError):
            _product(base_unit_id="")

    def test_internal_cannot_be_sellable(self):
        with pytest.raises(ProductsDomainError):
            _product(internal_only=True, sellable=True)

    def test_no_stock_or_price_fields(self):
        # Guardrail de dominio: Product no almacena existencia ni precio final.
        p = _product()
        for forbidden in ("existencia", "stock", "precio", "price", "cantidad_actual"):
            assert not hasattr(p, forbidden)


# ── roles derivados (§5) ─────────────────────────────────────────────────────
class TestRoles:
    def test_sellable_purchasable_roles(self):
        p = _product(sellable=True, purchasable=True, inventory_managed=True)
        assert ProductRole.SELLABLE in p.roles
        assert ProductRole.PURCHASABLE in p.roles
        assert ProductRole.INVENTORY_MANAGED in p.roles

    def test_internal_role(self):
        p = _product(internal_only=True, inventory_managed=True)
        assert ProductRole.INTERNAL_ONLY in p.roles
        assert ProductRole.SELLABLE not in p.roles


# ── clasificación cárnica mínima (§11, PROD-2) ───────────────────────────────
class TestMeatFlag:
    def test_meat_type_is_meat(self):
        p = _product(product_type=ProductType.PRIMARY_CUT, species_id="sp-bovino")
        assert p.is_meat is True

    def test_meat_submit_requires_species(self):
        p = _product(product_type=ProductType.PRIMARY_CUT, species_id=None)
        with pytest.raises(SpeciesRequiredError):
            p.submit()

    def test_resale_is_not_meat(self):
        assert _product().is_meat is False


# ── ciclo de vida (§10) ──────────────────────────────────────────────────────
class TestLifecycle:
    def test_full_happy_path(self):
        p = _product()
        assert p.lifecycle_status is LifecycleStatus.DRAFT
        p.submit()
        assert p.lifecycle_status is LifecycleStatus.UNDER_REVIEW
        p.activate()
        assert p.is_active() and p.activated_at

    def test_cannot_activate_incomplete(self):
        p = _product(category_id=None)
        with pytest.raises(ProductIncompleteError):
            p.activate()

    def test_illegal_transition_raises(self):
        p = _product()
        p.submit()
        p.activate()
        with pytest.raises(InvalidProductStateError):
            p.submit()  # ACTIVE → UNDER_REVIEW no permitido

    def test_block_and_unblock(self):
        p = _product()
        p.activate()
        p.block()
        assert p.lifecycle_status is LifecycleStatus.BLOCKED
        p.unblock()
        assert p.is_active()

    def test_discontinue_sets_timestamp_and_blocks_reactivation(self):
        p = _product()
        p.activate()
        p.discontinue()
        assert p.lifecycle_status is LifecycleStatus.DISCONTINUED and p.discontinued_at
        with pytest.raises(InvalidProductStateError):
            p.activate()  # DISCONTINUED → ACTIVE no permitido

    def test_archived_is_terminal(self):
        assert allowed_targets(LifecycleStatus.ARCHIVED) == frozenset()

    def test_transition_table(self):
        assert can_transition(LifecycleStatus.ACTIVE, LifecycleStatus.BLOCKED)
        assert not can_transition(LifecycleStatus.DISCONTINUED, LifecycleStatus.ACTIVE)

    def test_sellable_now_requires_active_and_sellable(self):
        p = _product(sellable=True)
        assert not p.is_sellable_now()  # aún DRAFT
        p.activate()
        assert p.is_sellable_now()


# ── creation policy (§7) ─────────────────────────────────────────────────────
class TestCreationPolicy:
    def test_valid_creation(self):
        validate_creation(product_type=ProductType.RESALE_PRODUCT,
                          base_unit_id="u1", species_id=None,
                          sellable=True, internal_only=False)

    def test_meat_requires_species(self):
        with pytest.raises(SpeciesRequiredError):
            validate_creation(product_type=ProductType.OFFAL, base_unit_id="u1",
                              species_id=None, sellable=False, internal_only=False)

    def test_missing_unit_rejected(self):
        with pytest.raises(ProductsDomainError):
            validate_creation(product_type=ProductType.SERVICE, base_unit_id=None,
                              species_id=None, sellable=True, internal_only=False)

    def test_bad_type_rejected(self):
        with pytest.raises(InvalidProductTypeError):
            validate_creation(product_type="NOPE", base_unit_id="u1",
                              species_id=None, sellable=True, internal_only=False)


# ── eventos canónicos (§46) ──────────────────────────────────────────────────
class TestEvents:
    def test_no_legacy_spanish_events(self):
        assert "PRODUCTO_CREADO" not in ALL_PRODUCT_EVENTS
        assert "RECETA_CREADA" not in ALL_PRODUCT_EVENTS

    def test_lifecycle_events_present(self):
        for e in (ProductEvents.PRODUCT_CREATED, ProductEvents.PRODUCT_ACTIVATED,
                  ProductEvents.PRODUCT_DISCONTINUED):
            assert e in ALL_PRODUCT_EVENTS
