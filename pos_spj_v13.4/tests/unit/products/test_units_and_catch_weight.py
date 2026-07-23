"""PROD-5 — unidades, conversiones Decimal (sin ciclos) y peso variable."""

from decimal import Decimal

import pytest

from backend.domain.products.entities.product_unit_conversion import (
    ProductUnitConversion,
)
from backend.domain.products.entities.unit_of_measure import UnitOfMeasure
from backend.domain.products.exceptions import (
    InvalidCatchWeightConfigurationError,
    InvalidUnitConversionError,
    InvalidUnitOfMeasureError,
    UnitConversionCycleError,
    UnitConversionNotFoundError,
)
from backend.domain.products.policies.unit_conversion_policy import (
    convert,
    detect_cycle,
)
from backend.domain.products.unit_enums import PriceBasis, UnitDimension
from backend.domain.products.value_objects.catch_weight_configuration import (
    CatchWeightConfiguration,
)


# ── unidades (§15) ───────────────────────────────────────────────────────────
class TestUnitOfMeasure:
    def test_unit_ok_and_normalized(self):
        u = UnitOfMeasure(code="kg", name="Kilogramo", dimension=UnitDimension.WEIGHT)
        assert u.code == "KG" and len(u.id) >= 32

    def test_unit_requires_code(self):
        with pytest.raises(InvalidUnitOfMeasureError):
            UnitOfMeasure(code="", name="x", dimension=UnitDimension.COUNT)

    def test_unit_bad_dimension(self):
        with pytest.raises(InvalidUnitOfMeasureError):
            UnitOfMeasure(code="PZA", name="Pieza", dimension="NOPE")


# ── conversiones (§16) ───────────────────────────────────────────────────────
class TestConversion:
    def test_factor_must_be_decimal_not_float(self):
        with pytest.raises(InvalidUnitConversionError):
            ProductUnitConversion(from_unit_id="a", to_unit_id="b", factor=20.0)

    def test_factor_must_be_positive(self):
        with pytest.raises(InvalidUnitConversionError):
            ProductUnitConversion(from_unit_id="a", to_unit_id="b", factor=Decimal("0"))

    def test_same_unit_rejected(self):
        with pytest.raises(InvalidUnitConversionError):
            ProductUnitConversion(from_unit_id="a", to_unit_id="a", factor=Decimal("1"))

    def test_convert_uses_decimal(self):
        c = ProductUnitConversion(from_unit_id="caja", to_unit_id="kg",
                                  factor=Decimal("20"), rounding_scale=3)
        assert c.convert(Decimal("2")) == Decimal("40.000")

    def test_inverse_factor(self):
        c = ProductUnitConversion(from_unit_id="caja", to_unit_id="kg", factor=Decimal("20"))
        assert c.inverse_factor() == Decimal("1") / Decimal("20")


# ── policy: ciclos + camino ──────────────────────────────────────────────────
class TestConversionPolicy:
    def test_no_cycle_ok(self):
        convs = [
            ProductUnitConversion(from_unit_id="caja", to_unit_id="paquete", factor=Decimal("6")),
            ProductUnitConversion(from_unit_id="paquete", to_unit_id="pza", factor=Decimal("10")),
        ]
        detect_cycle(convs)  # no raise

    def test_cycle_detected(self):
        convs = [
            ProductUnitConversion(from_unit_id="a", to_unit_id="b", factor=Decimal("2")),
            ProductUnitConversion(from_unit_id="b", to_unit_id="c", factor=Decimal("2")),
            ProductUnitConversion(from_unit_id="c", to_unit_id="a", factor=Decimal("2")),
        ]
        with pytest.raises(UnitConversionCycleError):
            detect_cycle(convs)

    def test_multi_hop_conversion(self):
        convs = [
            ProductUnitConversion(from_unit_id="caja", to_unit_id="paquete", factor=Decimal("6")),
            ProductUnitConversion(from_unit_id="paquete", to_unit_id="pza", factor=Decimal("10")),
        ]
        # 1 caja = 6 paquetes = 60 pza
        assert convert(Decimal("1"), from_unit_id="caja", to_unit_id="pza",
                       conversions=convs, rounding_scale=0) == Decimal("60")

    def test_inverse_path_conversion(self):
        convs = [ProductUnitConversion(from_unit_id="caja", to_unit_id="kg", factor=Decimal("20"))]
        # 40 kg = 2 cajas (camino inverso)
        assert convert(Decimal("40"), from_unit_id="kg", to_unit_id="caja",
                       conversions=convs, rounding_scale=2) == Decimal("2.00")

    def test_same_unit_returns_quantity(self):
        assert convert(Decimal("5"), from_unit_id="kg", to_unit_id="kg",
                       conversions=[]) == Decimal("5")

    def test_no_path_raises(self):
        with pytest.raises(UnitConversionNotFoundError):
            convert(Decimal("1"), from_unit_id="kg", to_unit_id="litro", conversions=[])

    def test_float_quantity_rejected(self):
        with pytest.raises(UnitConversionNotFoundError):
            convert(1.0, from_unit_id="a", to_unit_id="b", conversions=[])


# ── peso variable (§12) ──────────────────────────────────────────────────────
class TestCatchWeight:
    def _cfg(self, **kw):
        base = dict(enabled=True, nominal_unit_id="pza", weight_unit_id="kg",
                    minimum_weight=Decimal("1.0"), maximum_weight=Decimal("2.0"),
                    average_weight=Decimal("1.5"), tolerance_pct=Decimal("10"))
        base.update(kw)
        return CatchWeightConfiguration(**base)

    def test_valid_config(self):
        cfg = self._cfg()
        assert cfg.price_basis is PriceBasis.PER_KILOGRAM
        assert cfg.is_weight_in_range(Decimal("1.5"))

    def test_disabled_config_needs_no_range(self):
        cfg = CatchWeightConfiguration(enabled=False, nominal_unit_id="",
                                       weight_unit_id="", minimum_weight=Decimal("0"),
                                       maximum_weight=Decimal("0"))
        assert cfg.is_weight_in_range(Decimal("999"))

    def test_float_weight_rejected(self):
        with pytest.raises(InvalidCatchWeightConfigurationError):
            self._cfg(minimum_weight=1.0)

    def test_min_over_max_rejected(self):
        with pytest.raises(InvalidCatchWeightConfigurationError):
            self._cfg(minimum_weight=Decimal("3"), maximum_weight=Decimal("2"),
                      average_weight=None)

    def test_average_out_of_range_rejected(self):
        with pytest.raises(InvalidCatchWeightConfigurationError):
            self._cfg(average_weight=Decimal("5"))

    def test_tolerance_bounds(self):
        with pytest.raises(InvalidCatchWeightConfigurationError):
            self._cfg(tolerance_pct=Decimal("150"))

    def test_weight_within_tolerance(self):
        cfg = self._cfg(tolerance_pct=Decimal("10"))
        # rango [1,2], span 1, margen 0.1 → [0.9, 2.1]
        assert cfg.is_weight_in_range(Decimal("2.05"))
        assert not cfg.is_weight_in_range(Decimal("2.2"))

    def test_requires_units_when_enabled(self):
        with pytest.raises(InvalidCatchWeightConfigurationError):
            self._cfg(nominal_unit_id="")

    def test_price_basis_per_piece(self):
        cfg = self._cfg(price_basis=PriceBasis.PER_PIECE_WITH_ACTUAL_WEIGHT)
        assert cfg.price_basis is PriceBasis.PER_PIECE_WITH_ACTUAL_WEIGHT
