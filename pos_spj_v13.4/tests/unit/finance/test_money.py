"""Money value object — Decimal precision, currency safety, no floats."""

from decimal import Decimal

import pytest

from backend.domain.finance.exceptions import CurrencyMismatchError, InvalidMoneyError
from backend.domain.finance.value_objects.money import Money


class TestMoneyConstruction:
    def test_from_string_parses_decimal(self):
        money = Money.from_string("125.40")
        assert money.amount == Decimal("125.40")
        assert money.currency_code == "MXN"

    def test_rejects_float(self):
        with pytest.raises(InvalidMoneyError):
            Money(1.5)  # type: ignore[arg-type]

    def test_rejects_nan_and_infinity(self):
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("NaN"))
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("Infinity"))

    def test_rejects_invalid_string(self):
        with pytest.raises(InvalidMoneyError):
            Money.from_string("no-es-numero")

    def test_quantizes_to_two_places_half_up(self):
        assert Money.from_string("10.005").amount == Decimal("10.01")
        assert Money.from_string("10.004").amount == Decimal("10.00")

    def test_no_binary_float_drift(self):
        # 0.1 + 0.2 == 0.3 exactly — the classic float failure must not occur.
        total = Money.from_string("0.1").add(Money.from_string("0.2"))
        assert total.amount == Decimal("0.3")


class TestMoneyArithmetic:
    def test_add_subtract(self):
        a = Money.from_string("100.50")
        b = Money.from_string("0.50")
        assert a.add(b).to_string() == "101.00"
        assert a.subtract(b).to_string() == "100.00"

    def test_multiply_rejects_float(self):
        with pytest.raises(InvalidMoneyError):
            Money.from_string("10").multiply(1.5)  # type: ignore[arg-type]

    def test_multiply_decimal(self):
        assert Money.from_string("10").multiply(Decimal("0.16")).to_string() == "1.60"

    def test_currency_mismatch_raises(self):
        with pytest.raises(CurrencyMismatchError):
            Money.from_string("1", "MXN").add(Money.from_string("1", "USD"))
        with pytest.raises(CurrencyMismatchError):
            _ = Money.from_string("1", "MXN") > Money.from_string("1", "USD")


class TestMoneySerialization:
    def test_to_string_is_canonical_decimal(self):
        assert Money.from_string("125.4").to_string() == "125.40"
        assert Money.from_string("0").to_string() == "0.00"

    def test_immutability(self):
        money = Money.from_string("5")
        with pytest.raises(Exception):
            money.amount = Decimal("9")  # type: ignore[misc]
