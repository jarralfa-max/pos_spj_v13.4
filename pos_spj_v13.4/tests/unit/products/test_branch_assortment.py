"""PROD-14 — sucursales/canales: sin duplicar producto, sin precio, canales de consumo."""

import pytest

from backend.domain.products.channel_enums import CONSUMER_CHANNELS, SalesChannel
from backend.domain.products.entities.assortment import Assortment, AssortmentProduct
from backend.domain.products.entities.branch_product import BranchProduct
from backend.domain.products.entities.product import Product
from backend.domain.products.enums import ProductType
from backend.domain.products.exceptions import (
    ChannelNotAllowedError,
    InvalidAssortmentError,
    InvalidBranchProductError,
)
from backend.domain.products.internal_enums import InternalStage
from backend.domain.products.policies.branch_assortment_policy import (
    can_offer,
    ensure_channel_allowed,
)


def _sellable():
    return Product(code="ABR", name="Refresco", product_type=ProductType.RESALE_PRODUCT,
                   base_unit_id="pza", category_id="c1", sellable=True)


def _internal():
    return Product(code="WIP-1", name="Masa", product_type=ProductType.SEMI_FINISHED_GOOD,
                   base_unit_id="kg", category_id="c1",
                   internal_stage=InternalStage.WORK_IN_PROGRESS)


# ── branch product (§29) ─────────────────────────────────────────────────────
class TestBranchProduct:
    def test_requires_product_and_branch(self):
        with pytest.raises(InvalidBranchProductError):
            BranchProduct(product_id="", branch_id="b1")
        with pytest.raises(InvalidBranchProductError):
            BranchProduct(product_id="p1", branch_id="")

    def test_no_price_or_stock_fields(self):
        bp = BranchProduct(product_id="p1", branch_id="b1")
        for forbidden in ("precio", "price", "precio_local", "stock", "existencia"):
            assert not hasattr(bp, forbidden)


# ── assortment (§29) ─────────────────────────────────────────────────────────
class TestAssortment:
    def test_channel_coercion(self):
        a = Assortment(name="POS Centro", channel="POS")
        assert a.channel is SalesChannel.POS

    def test_bad_channel_rejected(self):
        with pytest.raises(InvalidAssortmentError):
            Assortment(name="X", channel="NOPE")

    def test_assortment_product_requires_ids(self):
        with pytest.raises(InvalidAssortmentError):
            AssortmentProduct(assortment_id="", product_id="p1")


# ── channel policy (§13, §33) ────────────────────────────────────────────────
class TestChannelPolicy:
    def test_consumer_channels_set(self):
        assert SalesChannel.POS in CONSUMER_CHANNELS
        assert SalesChannel.CENTRAL_WAREHOUSE not in CONSUMER_CHANNELS

    def test_sellable_allowed_in_pos(self):
        ensure_channel_allowed(_sellable(), SalesChannel.POS)

    def test_internal_blocked_in_pos(self):
        with pytest.raises(ChannelNotAllowedError):
            ensure_channel_allowed(_internal(), SalesChannel.POS)

    def test_internal_allowed_in_plant(self):
        ensure_channel_allowed(_internal(), SalesChannel.PLANT)  # no raise

    def test_non_sellable_blocked_in_ecommerce(self):
        p = Product(code="RAW", name="Materia prima", product_type=ProductType.RAW_MATERIAL,
                    base_unit_id="kg", category_id="c1")  # sellable=False
        assert not can_offer(p, SalesChannel.ECOMMERCE)

    def test_can_offer_true_for_sellable_delivery(self):
        assert can_offer(_sellable(), SalesChannel.DELIVERY)
