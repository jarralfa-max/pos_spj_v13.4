"""INV-9 — cold chain domain tests (range VO, policy, entities)."""

from decimal import Decimal

import pytest

from backend.domain.inventory.entities.cold_chain import (
    TemperatureExcursion,
    TemperatureReading,
)
from backend.domain.inventory.enums import (
    ColdChainStatus,
    ExcursionAction,
    TemperaturePoint,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.domain.inventory.policies.cold_chain_policy import ColdChainPolicy
from backend.domain.inventory.value_objects.cold_chain import ColdChainRange

# refrigerated meat band: 0–4 °C, warn ±1
FRESH = ColdChainRange(min_temp=Decimal("0"), max_temp=Decimal("4"),
                       warning_margin=Decimal("1"))


class TestColdChainRange:
    def test_compliant_and_warning_and_out(self):
        assert FRESH.is_compliant(Decimal("2"))
        assert not FRESH.is_compliant(Decimal("5"))
        assert FRESH.is_within_warning(Decimal("4.5"))
        assert not FRESH.is_within_warning(Decimal("6"))

    def test_rejects_float(self):
        with pytest.raises(InventoryDomainError):
            ColdChainRange(min_temp=0.0, max_temp=4)

    def test_max_below_min_invalid(self):
        with pytest.raises(InventoryDomainError):
            ColdChainRange(min_temp=Decimal("4"), max_temp=Decimal("0"))

    def test_freezer_negative_band(self):
        frozen = ColdChainRange(min_temp=Decimal("-20"), max_temp=Decimal("-16"))
        assert frozen.is_compliant(Decimal("-18"))
        assert not frozen.is_compliant(Decimal("-5"))


class TestColdChainPolicy:
    def setup_method(self):
        self.pol = ColdChainPolicy()

    def test_classify(self):
        assert self.pol.classify(Decimal("2"), FRESH) is ColdChainStatus.COMPLIANT
        assert self.pol.classify(Decimal("4.5"), FRESH) is ColdChainStatus.WARNING
        assert self.pol.classify(Decimal("8"), FRESH) is ColdChainStatus.OUT_OF_RANGE

    def test_decide_action(self):
        assert self.pol.decide_action(ColdChainStatus.COMPLIANT) is ExcursionAction.NONE
        assert self.pol.decide_action(ColdChainStatus.WARNING) is ExcursionAction.WARN
        assert self.pol.decide_action(ColdChainStatus.OUT_OF_RANGE) is ExcursionAction.WARN
        assert self.pol.decide_action(ColdChainStatus.OUT_OF_RANGE, auto_block=True) \
            is ExcursionAction.QUARANTINE

    def test_is_excursion(self):
        assert not self.pol.is_excursion(ColdChainStatus.COMPLIANT)
        assert self.pol.is_excursion(ColdChainStatus.OUT_OF_RANGE)


class TestEntities:
    def test_reading_create(self):
        r = TemperatureReading.create(sensor_id="s1", warehouse_id="w1",
                                      temperature=Decimal("3"),
                                      reading_point=TemperaturePoint.STORAGE)
        assert len(r.id) == 36 and r.temperature == Decimal("3")

    def test_reading_requires_sensor(self):
        with pytest.raises(InventoryDomainError):
            TemperatureReading.create(sensor_id="", warehouse_id="w1", temperature=1,
                                      reading_point=TemperaturePoint.STORAGE)

    def test_excursion_create(self):
        e = TemperatureExcursion.create(
            reading_id="r1", warehouse_id="w1", status=ColdChainStatus.OUT_OF_RANGE,
            temperature=Decimal("9"), min_temp=Decimal("0"), max_temp=Decimal("4"),
            action_taken=ExcursionAction.QUARANTINE, lot_id="L1")
        assert e.action_taken is ExcursionAction.QUARANTINE and not e.resolved
