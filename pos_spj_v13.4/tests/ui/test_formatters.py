"""FASE DS-6 — shared formatter tests (pure display, es-MX)."""

from datetime import date, datetime, time
from decimal import Decimal

from frontend.desktop.formatters import (
    format_address,
    format_date,
    format_duration,
    format_money,
    format_percentage,
    format_phone,
    format_quantity,
    format_status,
    format_time,
)


class TestMoney:
    def test_basic(self):
        assert format_money(Decimal("1234.5")) == "$1,234.50"
        assert format_money("0") == "$0.00"
        assert format_money(1000000) == "$1,000,000.00"

    def test_empty_is_dash_not_zero(self):
        assert format_money(None) == "—"
        assert format_money("") == "—"

    def test_currency_code(self):
        assert format_money("10", "USD") == "US$10.00"
        assert format_money("10", "MXN", show_code=True) == "$10.00 MXN"


class TestQuantity:
    def test_unit_precision(self):
        assert format_quantity("12.5", "kg") == "12.500 kg"
        assert format_quantity(8, "piezas") == "8 piezas"

    def test_empty(self):
        assert format_quantity(None) == "—"


class TestPercentage:
    def test_display_and_ratio(self):
        assert format_percentage(16) == "16.0%"
        assert format_percentage(Decimal("0.16"), is_ratio=True) == "16.0%"

    def test_empty(self):
        assert format_percentage(None) == "—"


class TestDate:
    def test_styles(self):
        assert format_date(date(2026, 7, 17)) == "17/07/2026"
        assert format_date(date(2026, 7, 17), style="medium") == "17 jul 2026"
        assert format_date("2026-07-17T14:45:00", style="iso") == "2026-07-17"

    def test_empty(self):
        assert format_date(None) == "—"


class TestTime:
    def test_24h(self):
        assert format_time(time(8, 0)) == "08:00"
        assert format_time("2026-07-17T14:45:00") == "14:45"
        assert format_time("23:59") == "23:59"

    def test_empty(self):
        assert format_time(None) == "—"


class TestDuration:
    def test_human(self):
        assert format_duration(90) == "1h 30m"
        assert format_duration(45) == "45m"
        assert format_duration(60 * 24 + 30) == "1d 30m"

    def test_empty_or_zero(self):
        assert format_duration(0) == "—"
        assert format_duration(None) == "—"


class TestPhone:
    def test_mexico(self):
        assert format_phone("+525512345678") == "+52 55 1234 5678"

    def test_non_e164_passthrough(self):
        assert format_phone("5512345678") == "5512345678"
        assert format_phone(None) == "—"


class TestAddress:
    def test_join(self):
        parts = {"street": "Calle 12", "exterior_number": "34",
                 "interior_number": "3", "neighborhood": "Centro",
                 "city": "Puebla", "state": "Puebla", "postal_code": "72000"}
        assert format_address(parts) == "Calle 12 34 int 3, Centro, Puebla, Puebla, 72000"

    def test_empty(self):
        assert format_address(None) == "—"
        assert format_address({}) == "—"


class TestStatus:
    def test_labels(self):
        assert format_status("AUTHORIZED") == "Autorizado"
        assert format_status("PAID") == "Pagada"

    def test_unknown_passthrough(self):
        assert format_status("SOMETHING_NEW") == "SOMETHING_NEW"
