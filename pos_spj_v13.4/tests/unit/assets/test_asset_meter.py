"""ASSET-8 — AssetMeter and AssetMeterReading."""

from decimal import Decimal

import pytest

from backend.domain.assets.entities.asset_meter import AssetMeter
from backend.domain.assets.entities.asset_meter_reading import AssetMeterReading
from backend.domain.assets.enums import AssetMeterType
from backend.domain.assets.exceptions import AssetDomainError, MeterReadingInvalidError


class TestAssetMeter:
    def test_create_defaults_to_zero(self):
        meter = AssetMeter.create("asset-1", AssetMeterType.HOURS, "horas")
        assert meter.current_reading == Decimal("0")

    def test_advance_to_higher_reading(self):
        meter = AssetMeter.create("asset-1", AssetMeterType.KILOMETERS, "km")
        meter.advance_to(Decimal("1500"))
        assert meter.current_reading == Decimal("1500")

    def test_advance_to_lower_reading_fails(self):
        meter = AssetMeter.create("asset-1", AssetMeterType.KILOMETERS, "km")
        meter.advance_to(Decimal("1500"))
        with pytest.raises(MeterReadingInvalidError):
            meter.advance_to(Decimal("1000"))

    def test_advance_to_rejects_float(self):
        meter = AssetMeter.create("asset-1", AssetMeterType.HOURS, "horas")
        with pytest.raises(AssetDomainError):
            meter.advance_to(10.5)


class TestAssetMeterReading:
    def test_create_reading(self):
        reading = AssetMeterReading.create("meter-1", "asset-1", Decimal("120.5"),
                                           "tech-1", "op-1")
        assert reading.reading_value == Decimal("120.5")

    def test_negative_reading_fails(self):
        with pytest.raises(AssetDomainError):
            AssetMeterReading.create("meter-1", "asset-1", Decimal("-1"), "tech-1", "op-1")

    def test_float_reading_fails(self):
        with pytest.raises(AssetDomainError):
            AssetMeterReading.create("meter-1", "asset-1", 10.5, "tech-1", "op-1")
