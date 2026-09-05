"""ASSET-2 (§83, §110) — Activos defines data scopes (OWN/ASSIGNED/BRANCH/
REGION/COMPANY/ALL) rather than trusting caller-supplied filters."""

from __future__ import annotations

from backend.application.assets.scopes import AssetDataScope, AssetScopeLevel


def test_asset_scope_levels_cover_master_prompt_vocabulary():
    expected = {"OWN", "ASSIGNED", "BRANCH", "REGION", "COMPANY", "ALL"}
    actual = {level.value for level in AssetScopeLevel}
    assert actual == expected


def test_asset_data_scope_is_immutable_value_object():
    scope = AssetDataScope(level=AssetScopeLevel.BRANCH, branch_ids=("b1",))
    assert scope.level is AssetScopeLevel.BRANCH
    assert scope.branch_ids == ("b1",)
    try:
        scope.level = AssetScopeLevel.ALL  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("AssetDataScope debe ser inmutable (frozen dataclass)")
