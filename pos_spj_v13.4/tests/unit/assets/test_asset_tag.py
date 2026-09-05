"""ASSET-13 — AssetTag (etiquetas/QR)."""

import pytest

from backend.domain.assets.entities.asset_tag import AssetTag
from backend.domain.assets.enums import AssetTagStatus, AssetTagType
from backend.domain.assets.exceptions import AssetDomainError, AssetTagStateInvalidError


class TestAssetTagCreate:
    def test_create_generates_distinct_qr_token(self):
        tag = AssetTag.create("asset-1", "ACT-000001", "op-1")
        assert tag.qr_public_token != tag.id
        assert tag.qr_public_token != tag.asset_id
        assert tag.status is AssetTagStatus.ISSUED

    def test_requires_tag_number(self):
        with pytest.raises(AssetDomainError):
            AssetTag.create("asset-1", "", "op-1")

    def test_default_type_is_qr(self):
        tag = AssetTag.create("asset-1", "ACT-1", "op-1")
        assert tag.tag_type is AssetTagType.QR


class TestAssetTagLifecycle:
    def test_full_lifecycle(self):
        tag = AssetTag.create("asset-1", "ACT-1", "op-1")
        tag.mark_printed()
        assert tag.status is AssetTagStatus.PRINTED
        tag.activate()
        assert tag.is_active() is True

    def test_reprint_allowed(self):
        tag = AssetTag.create("asset-1", "ACT-1", "op-1")
        tag.mark_printed()
        tag.mark_printed()  # reimpresión controlada (§81 ASSETS_TAG_REPRINT)
        assert tag.status is AssetTagStatus.PRINTED

    def test_cannot_activate_before_printed(self):
        tag = AssetTag.create("asset-1", "ACT-1", "op-1")
        with pytest.raises(AssetTagStateInvalidError):
            tag.activate()

    def test_replace_from_active(self):
        tag = AssetTag.create("asset-1", "ACT-1", "op-1")
        tag.mark_printed()
        tag.activate()
        tag.replace("etiqueta dañada")
        assert tag.status is AssetTagStatus.REPLACED

    def test_void_from_issued(self):
        tag = AssetTag.create("asset-1", "ACT-1", "op-1")
        tag.void("error de captura")
        assert tag.status is AssetTagStatus.VOID

    def test_cannot_modify_terminal_tag(self):
        tag = AssetTag.create("asset-1", "ACT-1", "op-1")
        tag.void()
        with pytest.raises(AssetTagStateInvalidError):
            tag.void()
        with pytest.raises(AssetTagStateInvalidError):
            tag.mark_printed()
