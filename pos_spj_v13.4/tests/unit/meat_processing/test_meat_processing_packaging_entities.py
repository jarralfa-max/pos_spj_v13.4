from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.meat_processing.entities.packaging_execution import PackagingExecution
from backend.domain.meat_processing.entities.production_label import ProductionLabel
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError
from backend.shared.ids import new_uuid


# -- PackagingExecution --------------------------------------------------------

def _packaging(**overrides) -> PackagingExecution:
    base = dict(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=new_uuid(),
        product_id=new_uuid(), packaging_material_id=new_uuid(), package_quantity=10,
        net_weight=Decimal("9.5"), gross_weight=Decimal("10"), tare_weight=Decimal("0.5"),
        packaged_by_user_id=new_uuid())
    base.update(overrides)
    return PackagingExecution(**base)


def test_packaging_requires_positive_package_quantity():
    with pytest.raises(MeatProcessingInvariantError):
        _packaging(package_quantity=0)


def test_packaging_tare_cannot_exceed_gross():
    with pytest.raises(MeatProcessingInvariantError):
        _packaging(gross_weight=Decimal("1"), tare_weight=Decimal("2"), net_weight=Decimal("0.5"))


def test_packaging_net_cannot_exceed_gross():
    with pytest.raises(MeatProcessingInvariantError):
        _packaging(gross_weight=Decimal("1"), net_weight=Decimal("2"), tare_weight=Decimal("0"))


def test_packaging_expiration_must_be_after_production():
    now = datetime.now(timezone.utc)
    with pytest.raises(MeatProcessingInvariantError):
        _packaging(production_date=now, expiration_date=now - timedelta(days=1))


def test_packaging_accepts_valid_expiration():
    now = datetime.now(timezone.utc)
    packaging = _packaging(production_date=now, expiration_date=now + timedelta(days=30))
    assert packaging.expiration_date > packaging.production_date


def test_packaging_rejects_float():
    with pytest.raises(TypeError):
        _packaging(net_weight=9.5)


# -- ProductionLabel -----------------------------------------------------------

def _label(**overrides) -> ProductionLabel:
    base = dict(
        id=new_uuid(), operation_id=new_uuid(), packaging_execution_id=new_uuid(),
        label_template_id=new_uuid(), barcode="7501234567890",
        qr_traceability_reference="LPR-2026-000001")
    base.update(overrides)
    return ProductionLabel(**base)


def test_label_requires_barcode_and_qr_reference():
    with pytest.raises(MeatProcessingInvariantError):
        _label(barcode="  ")
    with pytest.raises(MeatProcessingInvariantError):
        _label(qr_traceability_reference="")


def test_label_first_print_sets_printed_at_without_reprint():
    label = _label()
    assert not label.is_printed
    actor = new_uuid()
    label.mark_printed(actor_user_id=actor)
    assert label.is_printed
    assert label.printed_by_user_id == actor
    assert label.reprint_count == 0


def test_label_second_print_increments_reprint_count():
    label = _label()
    label.mark_printed(actor_user_id=new_uuid())
    first_printed_at = label.printed_at
    reprinter = new_uuid()
    label.mark_printed(actor_user_id=reprinter)
    assert label.reprint_count == 1
    assert label.printed_at == first_printed_at  # first print time preserved
    assert label.printed_by_user_id == reprinter
