"""ORD-13 — OrderPackage (§29): creation, derived net_weight, seal/cancel
lifecycle."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.enums import PackageStatus, PackageType
from backend.domain.orders_delivery.exceptions import InvalidPackageError
from backend.domain.orders_delivery.package import OrderPackage
from backend.shared.ids import new_uuid


class TestOrderPackageCreation:
    def test_requires_at_least_one_line(self):
        with pytest.raises(InvalidPackageError):
            OrderPackage.create(
                order_id=new_uuid(), package_number="1", package_type=PackageType.BOX,
                line_ids=())

    def test_requires_package_number(self):
        with pytest.raises(InvalidPackageError):
            OrderPackage.create(
                order_id=new_uuid(), package_number="  ", package_type=PackageType.BOX,
                line_ids=(new_uuid(),))

    def test_gross_weight_cannot_be_less_than_tare(self):
        with pytest.raises(InvalidPackageError):
            OrderPackage.create(
                order_id=new_uuid(), package_number="1", package_type=PackageType.BOX,
                line_ids=(new_uuid(),), tare=Decimal("5"), gross_weight=Decimal("2"))

    def test_creates_with_open_status(self):
        package = OrderPackage.create(
            order_id=new_uuid(), package_number="1", package_type=PackageType.INSULATED_BOX,
            line_ids=(new_uuid(),), tare=Decimal("0.5"), gross_weight=Decimal("3.5"))
        assert package.status == PackageStatus.OPEN
        assert package.net_weight == Decimal("3.0")


class TestOrderPackageSeal:
    def test_seal_requires_seal_number(self):
        package = OrderPackage.create(
            order_id=new_uuid(), package_number="1", package_type=PackageType.BOX,
            line_ids=(new_uuid(),))
        with pytest.raises(InvalidPackageError):
            package.seal(seal_number="")

    def test_seal_sets_status_and_number(self):
        package = OrderPackage.create(
            order_id=new_uuid(), package_number="1", package_type=PackageType.BOX,
            line_ids=(new_uuid(),))
        package.seal(seal_number="SEAL-001")
        assert package.status == PackageStatus.SEALED
        assert package.seal_number == "SEAL-001"

    def test_cannot_seal_twice(self):
        package = OrderPackage.create(
            order_id=new_uuid(), package_number="1", package_type=PackageType.BOX,
            line_ids=(new_uuid(),))
        package.seal(seal_number="SEAL-001")
        with pytest.raises(InvalidPackageError):
            package.seal(seal_number="SEAL-002")


class TestOrderPackageCancel:
    def test_cancel_open_package(self):
        package = OrderPackage.create(
            order_id=new_uuid(), package_number="1", package_type=PackageType.BOX,
            line_ids=(new_uuid(),))
        package.cancel()
        assert package.status == PackageStatus.CANCELLED

    def test_cannot_cancel_sealed_package(self):
        package = OrderPackage.create(
            order_id=new_uuid(), package_number="1", package_type=PackageType.BOX,
            line_ids=(new_uuid(),))
        package.seal(seal_number="SEAL-001")
        with pytest.raises(InvalidPackageError):
            package.cancel()
