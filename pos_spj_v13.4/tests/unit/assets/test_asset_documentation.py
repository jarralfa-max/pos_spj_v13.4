"""ASSET-9 — AssetDocument, AssetWarranty, AssetInsurancePolicy."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.domain.assets.entities.asset_document import AssetDocument
from backend.domain.assets.entities.asset_insurance_policy import AssetInsurancePolicy
from backend.domain.assets.entities.asset_warranty import AssetWarranty
from backend.domain.assets.enums import AssetDocumentType, AssetInsuranceStatus, AssetWarrantyStatus
from backend.domain.assets.exceptions import AssetDomainError
from backend.domain.finance.value_objects.money import Money


class TestAssetDocument:
    def test_create_ok(self):
        doc = AssetDocument.create("asset-1", AssetDocumentType.INVOICE, "storage-ref-1",
                                   "application/pdf", 2048, "sha256:abc", "u1", "op-1")
        assert doc.mime_type == "application/pdf"

    def test_oversized_document_fails(self):
        with pytest.raises(AssetDomainError):
            AssetDocument.create("asset-1", AssetDocumentType.MANUAL, "ref", "application/pdf",
                                 26 * 1024 * 1024, "hash", "u1", "op-1")

    def test_zero_size_fails(self):
        with pytest.raises(AssetDomainError):
            AssetDocument.create("asset-1", AssetDocumentType.PHOTO, "ref", "image/jpeg",
                                 0, "hash", "u1", "op-1")


class TestAssetWarranty:
    def _warranty(self, **extra) -> AssetWarranty:
        return AssetWarranty.create("asset-1", "provider-1", "MANUFACTURER",
                                    date(2026, 1, 1), date(2027, 1, 1), "op-1", **extra)

    def test_expires_before_starts_fails(self):
        with pytest.raises(AssetDomainError):
            AssetWarranty.create("asset-1", "provider-1", "MANUFACTURER",
                                 date(2027, 1, 1), date(2026, 1, 1), "op-1")

    def test_refresh_status_active(self):
        w = self._warranty()
        w.refresh_status(as_of=date(2026, 6, 1))
        assert w.status is AssetWarrantyStatus.ACTIVE

    def test_refresh_status_expiring(self):
        w = self._warranty()
        w.refresh_status(as_of=date(2026, 12, 20))
        assert w.status is AssetWarrantyStatus.EXPIRING

    def test_refresh_status_expired(self):
        w = self._warranty()
        w.refresh_status(as_of=date(2027, 2, 1))
        assert w.status is AssetWarrantyStatus.EXPIRED

    def test_void_is_sticky(self):
        w = self._warranty()
        w.void("reemplazado por garantía extendida")
        w.refresh_status(as_of=date(2026, 6, 1))
        assert w.status is AssetWarrantyStatus.VOID


class TestAssetInsurancePolicy:
    def _policy(self, **extra) -> AssetInsurancePolicy:
        return AssetInsurancePolicy.create("asset-1", "Aseguradora X", "POL-001",
                                           Money(Decimal("50000")), date(2026, 1, 1),
                                           date(2027, 1, 1), "op-1", **extra)

    def test_requires_positive_insured_value(self):
        with pytest.raises(AssetDomainError):
            AssetInsurancePolicy.create("asset-1", "X", "POL-1", Money(Decimal("0")),
                                        date(2026, 1, 1), date(2027, 1, 1), "op-1")

    def test_cancel(self):
        p = self._policy()
        p.cancel("activo dado de baja")
        assert p.status is AssetInsuranceStatus.CANCELLED

    def test_cancel_twice_fails(self):
        p = self._policy()
        p.cancel()
        with pytest.raises(AssetDomainError):
            p.cancel()

    def test_refresh_status_expired_after_expiry(self):
        p = self._policy()
        p.refresh_status(as_of=date(2027, 2, 1))
        assert p.status is AssetInsuranceStatus.EXPIRED

    def test_cancelled_status_is_sticky(self):
        p = self._policy()
        p.cancel()
        p.refresh_status(as_of=date(2026, 6, 1))
        assert p.status is AssetInsuranceStatus.CANCELLED
