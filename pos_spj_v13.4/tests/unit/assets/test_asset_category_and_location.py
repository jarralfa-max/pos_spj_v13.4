"""ASSET-3 — AssetCategory and AssetLocation (configurable catalog + hierarchy)."""

import pytest

from backend.domain.assets.entities.asset_category import AssetCategory
from backend.domain.assets.entities.asset_location import AssetLocation
from backend.domain.assets.enums import AssetCategoryStatus, AssetLocationType
from backend.domain.assets.exceptions import AssetDomainError


class TestAssetCategory:
    def test_create_normalizes_code(self):
        cat = AssetCategory.create("Refrigeración", "refrigeracion")
        assert cat.code == "REFRIGERACION"
        assert cat.status is AssetCategoryStatus.ACTIVE

    def test_create_requires_name_and_code(self):
        with pytest.raises(AssetDomainError):
            AssetCategory.create("", "X")
        with pytest.raises(AssetDomainError):
            AssetCategory.create("X", "")

    def test_deactivate_reactivate(self):
        cat = AssetCategory.create("Mobiliario", "MOB")
        cat.deactivate()
        assert cat.is_active() is False
        cat.reactivate()
        assert cat.is_active() is True


class TestAssetLocation:
    def test_branch_level_does_not_require_parent(self):
        loc = AssetLocation.create("br-1", "SUC-QRO", "Sucursal Querétaro",
                                   AssetLocationType.BRANCH)
        assert loc.parent_location_id is None

    def test_sub_branch_level_requires_parent(self):
        with pytest.raises(AssetDomainError):
            AssetLocation.create("br-1", "AREA-1", "Cocina", AssetLocationType.AREA)

    def test_sub_branch_level_with_parent_ok(self):
        loc = AssetLocation.create("br-1", "AREA-1", "Cocina", AssetLocationType.AREA,
                                   parent_location_id="loc-branch")
        assert loc.parent_location_id == "loc-branch"

    def test_deactivate_reactivate(self):
        loc = AssetLocation.create("br-1", "SUC-QRO", "Sucursal Querétaro",
                                   AssetLocationType.BRANCH)
        loc.deactivate()
        assert loc.is_active() is False
        loc.reactivate()
        assert loc.is_active() is True
