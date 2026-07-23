"""PROD-13 — combos/kits/paquetes: virtual vs stocked, versionado, explosión, ciclos."""

from decimal import Decimal

import pytest

from backend.domain.products.bundle_enums import BundleType
from backend.domain.products.entities.bundle_component import BundleComponent
from backend.domain.products.entities.bundle_version import BundleVersion
from backend.domain.products.entities.product_bundle import ProductBundle
from backend.domain.products.exceptions import (
    BundleCycleDetectedError,
    InvalidBundleError,
    RecipeVersionImmutableError,
)
from backend.domain.products.services.bundle_explosion_service import (
    BundleExplosionService,
)


def _comp(pid="c1", qty="1", **kw):
    return BundleComponent(component_product_id=pid, quantity=Decimal(qty),
                           unit_id="kg", **kw)


# ── bundle master ────────────────────────────────────────────────────────────
class TestBundle:
    def test_virtual_vs_stocked(self):
        v = ProductBundle(product_id="P", bundle_type=BundleType.MEAT_BOX, name="Caja parrillera")
        k = ProductBundle(product_id="K", bundle_type=BundleType.STOCKED_KIT, name="Kit armado")
        assert v.is_virtual and not v.is_stocked
        assert k.is_stocked and not k.is_virtual

    def test_bundle_type_coercion(self):
        assert ProductBundle(product_id="P", bundle_type="GIFT_SET", name="X").bundle_type \
            is BundleType.GIFT_SET

    def test_requires_product_and_name(self):
        with pytest.raises(InvalidBundleError):
            ProductBundle(product_id="", bundle_type=BundleType.FIXED_COMBO, name="X")


# ── component ────────────────────────────────────────────────────────────────
class TestComponent:
    def test_float_rejected(self):
        with pytest.raises(InvalidBundleError):
            BundleComponent(component_product_id="c1", quantity=1.0, unit_id="kg")

    def test_positive_qty(self):
        with pytest.raises(InvalidBundleError):
            _comp(qty="0")


# ── version (§22) ────────────────────────────────────────────────────────────
class TestVersion:
    def _draft(self):
        v = BundleVersion(bundle_id="b1", version_number=1)
        v.add_component(_comp("bistec")); v.add_component(_comp("chorizo", qty="0.5"))
        return v

    def test_lifecycle_and_immutability(self):
        v = self._draft()
        v.submit(); v.approve(approved_by_user_id="mgr"); v.activate()
        assert v.status.value == "ACTIVE"
        with pytest.raises(RecipeVersionImmutableError):
            v.add_component(_comp("x"))

    def test_cannot_submit_empty(self):
        v = BundleVersion(bundle_id="b1", version_number=1)
        with pytest.raises(InvalidBundleError):
            v.submit()


# ── explosion + validation (§28) ────────────────────────────────────────────
class TestExplosion:
    def _bundle(self, pid="P"):
        return ProductBundle(product_id=pid, bundle_type=BundleType.MEAT_BOX, name="Caja")

    def test_valid_bundle(self):
        v = BundleVersion(bundle_id="b1", version_number=1)
        v.add_component(_comp("bistec")); v.add_component(_comp("costilla"))
        BundleExplosionService().validate(self._bundle(), v)

    def test_self_containing_rejected(self):
        v = BundleVersion(bundle_id="b1", version_number=1)
        v.add_component(_comp("P"))
        with pytest.raises(BundleCycleDetectedError):
            BundleExplosionService().validate(self._bundle("P"), v)

    def test_transitive_cycle(self):
        v = BundleVersion(bundle_id="b1", version_number=1)
        v.add_component(_comp("K"))
        graph = {"K": ["P"]}
        with pytest.raises(BundleCycleDetectedError):
            BundleExplosionService().validate(self._bundle("P"), v,
                                              resolver=lambda p: graph.get(p, []))

    def test_duplicate_component_rejected(self):
        v = BundleVersion(bundle_id="b1", version_number=1)
        v.add_component(_comp("bistec")); v.add_component(_comp("bistec"))
        with pytest.raises(InvalidBundleError):
            BundleExplosionService().validate(self._bundle(), v)

    def test_explode_scales(self):
        v = BundleVersion(bundle_id="b1", version_number=1)
        v.add_component(_comp("bistec", qty="1"))
        v.add_component(_comp("chorizo", qty="0.5"))
        result = BundleExplosionService().explode(v, Decimal("3"))
        qty = {e.component_product_id: e.quantity for e in result}
        assert qty["bistec"] == Decimal("3") and qty["chorizo"] == Decimal("1.5")

    def test_explode_excludes_optional_by_default(self):
        v = BundleVersion(bundle_id="b1", version_number=1)
        v.add_component(_comp("bistec"))
        v.add_component(_comp("salsa", optional=True))
        assert {e.component_product_id for e in BundleExplosionService().explode(v)} == {"bistec"}
        assert {e.component_product_id for e in
                BundleExplosionService().explode(v, include_optional=True)} == {"bistec", "salsa"}
