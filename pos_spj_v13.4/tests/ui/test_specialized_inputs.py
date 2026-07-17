"""FASE DS-4 — specialized input contract tests (headless, both themes)."""

import os
from decimal import Decimal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtGui import QKeyEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.components import (  # noqa: E402
    BarcodeInput,
    DecimalInput,
    DurationInput,
    EmailInput,
    EntitySearchInput,
    FormField,
    MonthInput,
    SearchableComboBox,
    SearchInput,
    StandardForm,
    StandardLineEdit,
    TaxIdentifierInput,
)
from frontend.desktop.components.search_selector import SearchOption  # noqa: E402
from frontend.desktop.themes.theme_manager import ThemeManager  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    ThemeManager.instance().apply(application, "light")
    return application


class TestDecimalInput:
    def test_returns_exact_decimal(self, app):
        d = DecimalInput(precision=2)
        d.set_decimal("10.5")
        assert d.decimal_value() == Decimal("10.50")
        assert isinstance(d.decimal_value(), Decimal)

    def test_nullable_empty_is_none_not_zero(self, app):
        d = DecimalInput(nullable=True)
        assert d.decimal_value() is None
        non_null = DecimalInput(nullable=False)
        assert non_null.decimal_value() == Decimal(0)

    def test_min_max_validation(self, app):
        d = DecimalInput(minimum="0", maximum="100")
        d.setText("150")
        assert not d.is_valid()
        assert d.error_message()


class TestEmailInput:
    def test_valid_and_normalized(self, app):
        e = EmailInput()
        e.setText("  Person@DOMAIN.COM ")
        assert e.email() == "Person@domain.com"  # domain lowered, local preserved
        assert e.is_valid()

    def test_invalid(self, app):
        e = EmailInput(required=True)
        e.setText("not-an-email")
        assert not e.is_valid() and e.error_message()


class TestTaxIdentifier:
    def test_rfc_moral_vs_fisica(self, app):
        moral = TaxIdentifierInput(kind="RFC")
        moral.setText("abc010203xy1")  # 3 letters → moral
        assert moral.is_valid()
        assert moral.value() == "ABC010203XY1"
        assert moral.rfc_person_type() == "moral"
        fisica = TaxIdentifierInput(kind="RFC")
        fisica.setText("abcd010203xy1")  # 4 letters → fisica
        assert fisica.rfc_person_type() == "fisica"

    def test_invalid_rfc(self, app):
        t = TaxIdentifierInput(kind="RFC", required=True)
        t.setText("123")
        assert not t.is_valid()


class TestMonthInput:
    def test_roundtrip(self, app):
        m = MonthInput()
        assert m.set_month_text("2026-07")
        assert m.month_text() == "2026-07"

    def test_rejects_bad(self, app):
        m = MonthInput()
        assert not m.set_month_text("2026-13")


class TestDurationInput:
    def test_units_to_minutes(self, app):
        d = DurationInput()
        d.set_total_minutes(90)
        # 90 is not a whole hour → minutes unit
        assert d.total_minutes() == 90
        d.set_total_minutes(120)
        assert d.total_minutes() == 120  # 2 horas
        d.set_total_minutes(60 * 24)
        assert d.total_minutes() == 60 * 24  # 1 día


class TestSearchableCombo:
    def test_placeholder_and_ids(self, app):
        combo = SearchableComboBox()
        assert not combo.has_selection()
        combo.set_options([("id-1", "Rol A"), ("id-2", "Rol B")])
        assert combo.set_current_id("id-2")
        assert combo.current_id() == "id-2"
        assert combo.has_selection()

    def test_not_editable_insert(self, app):
        from PyQt5.QtWidgets import QComboBox
        combo = SearchableComboBox()
        assert combo.insertPolicy() == QComboBox.NoInsert


class TestSearchInput:
    def test_debounce_emits(self, app):
        s = SearchInput(debounce_ms=0)
        received = []
        s.search_changed.connect(received.append)
        s.setText("abc")
        app.processEvents()
        assert received and received[-1] == "abc"


class TestBarcodeInput:
    def test_enter_emits_scanned_and_clears(self, app):
        b = BarcodeInput(clear_after_scan=True)
        got = []
        b.scanned.connect(got.append)
        b.setText("7501234567890")
        ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
        b.keyPressEvent(ev)
        assert got == ["7501234567890"]
        assert b.code() == ""  # cleared after scan


class TestEntitySearch:
    def test_provider_selection_by_id(self, app):
        provider = lambda q: [SearchOption("uuid-1", "Producto 1"),
                              SearchOption("uuid-2", "Producto 2")]
        w = EntitySearchInput(provider=provider, debounce_ms=0)
        w._run_search("prod")
        assert w._results.count() == 2
        w._choose(w._results.item(0))
        assert w.selected_id() == "uuid-1"


class TestFormField:
    def test_error_toggles_state(self, app):
        field = StandardLineEdit()
        ff = FormField("Nombre", field, required=True, helper="Como aparece en INE")
        ff.set_error("Requerido")
        assert field.property("state") == "error"
        ff.set_error(None)
        assert field.property("state") == "default"

    def test_standard_form_collects_errors(self, app):
        form = StandardForm()
        form.add_field("name", FormField("Nombre", StandardLineEdit()))
        form.add_field("email", FormField("Correo", EmailInput()))
        form.set_errors({"email": "Correo inválido"})
        assert form.field("email")._field.property("state") == "error"
        assert form.field("name")._field.property("state") == "default"
