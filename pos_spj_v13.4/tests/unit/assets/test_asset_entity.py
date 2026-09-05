"""ASSET-3 — Asset aggregate lifecycle (registration, commissioning, status/condition transitions)."""

from datetime import date

import pytest

from backend.domain.assets.entities.asset import Asset
from backend.domain.assets.enums import AssetCondition, AssetCriticality, AssetStatus
from backend.domain.assets.exceptions import AssetDomainError, AssetStateInvalidError


def _asset(**extra) -> Asset:
    return Asset.create("ACT-000001", "Refrigerador vertical", "cat-1", "op-1",
                        created_by_user_id="u1", origin_branch_id="br-1", **extra)


class TestAssetCreate:
    def test_create_defaults(self):
        a = _asset()
        assert a.status is AssetStatus.DRAFT
        assert a.condition is AssetCondition.NEW
        assert a.criticality is AssetCriticality.MEDIUM
        assert a.current_branch_id == "br-1"

    def test_create_requires_asset_number(self):
        with pytest.raises(AssetDomainError):
            Asset.create("", "x", "cat-1", "op-1")

    def test_create_requires_category(self):
        with pytest.raises(AssetDomainError):
            Asset.create("ACT-1", "x", "", "op-1")


class TestAssetLifecycle:
    def test_commission_from_draft(self):
        a = _asset()
        a.commission(operational_start_date=date(2026, 1, 1))
        assert a.status is AssetStatus.AVAILABLE
        assert a.commissioned_at is not None
        assert a.operational_start_date == date(2026, 1, 1)

    def test_commission_twice_fails(self):
        a = _asset()
        a.commission()
        with pytest.raises(AssetStateInvalidError):
            a.commission()

    def test_suspend_and_reactivate(self):
        a = _asset()
        a.commission()
        a.suspend("mantenimiento externo")
        assert a.status is AssetStatus.OUT_OF_SERVICE
        a.reactivate()
        assert a.status is AssetStatus.AVAILABLE

    def test_suspend_from_draft_fails(self):
        a = _asset()
        with pytest.raises(AssetStateInvalidError):
            a.suspend()

    def test_reactivate_requires_out_of_service(self):
        a = _asset()
        a.commission()
        with pytest.raises(AssetStateInvalidError):
            a.reactivate()

    def test_change_condition_and_criticality(self):
        a = _asset()
        a.change_condition(AssetCondition.FAIR)
        a.change_criticality(AssetCriticality.HIGH)
        assert a.condition is AssetCondition.FAIR
        assert a.criticality is AssetCriticality.HIGH

    def test_relocate_updates_branch_and_location(self):
        a = _asset()
        a.relocate("br-2", "loc-9")
        assert a.current_branch_id == "br-2"
        assert a.current_location_id == "loc-9"

    def test_is_available_for_assignment(self):
        a = _asset()
        assert a.is_available_for_assignment() is False
        a.commission()
        assert a.is_available_for_assignment() is True
