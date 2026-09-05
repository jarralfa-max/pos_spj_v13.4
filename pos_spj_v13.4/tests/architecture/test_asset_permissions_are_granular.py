"""ASSET-1/ASSET-2 (§71-82, §110) — Activos permissions must be granular, not
a single catch-all gate."""

from __future__ import annotations

from backend.application.assets.permissions import ALL_ASSET_PERMISSIONS, AssetPermissions


def test_asset_permissions_are_granular():
    assert len(ALL_ASSET_PERMISSIONS) >= 60
    for code in (
        AssetPermissions.DISPOSAL_APPROVE,
        AssetPermissions.WORK_ORDER_COMPLETE,
        AssetPermissions.TRANSFER_RECEIVE,
        AssetPermissions.CAPITALIZATION_PROPOSAL_CREATE,
        AssetPermissions.PHYSICAL_INVENTORY_COUNT,
    ):
        assert code in ALL_ASSET_PERMISSIONS


def test_every_asset_permission_is_activos_prefixed_string():
    for code in ALL_ASSET_PERMISSIONS:
        assert isinstance(code, str) and code.startswith("ACTIVOS.")


def test_asset_permissions_never_grant_journal_or_treasury_actions():
    forbidden_fragments = ("asiento", "tesoreria.transferir", "pago.ejecutar", "pago.autorizar")
    for code in ALL_ASSET_PERMISSIONS:
        lowered = code.lower()
        for fragment in forbidden_fragments:
            assert fragment not in lowered, (
                f"Permiso de Activos {code!r} invade la frontera financiera "
                f"(fragmento prohibido: {fragment!r})"
            )
