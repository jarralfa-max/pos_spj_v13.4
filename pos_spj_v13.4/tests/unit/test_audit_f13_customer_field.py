"""Auditoría CRM F13: al escribir otro texto se pierde la selección anterior."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip("PyQt5.QtWidgets")

from frontend.desktop.components.search_selector import SearchOption  # noqa: E402
from frontend.desktop.modules.customers_crm.forms import (  # noqa: E402
    CrmFormDialog,
    FieldSpec,
    _CustomerField,
)


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _field():
    options = [SearchOption(id="A", label="Cliente A"), SearchOption(id="B", label="Cliente B")]
    return _CustomerField(lambda q: [o for o in options if q.lower() in o.label.lower()])


def test_typing_after_selecting_clears_the_selection(app):
    field = _field()
    field._box.selected.emit(SearchOption(id="A", label="Cliente A"))
    assert field.value() == "A"
    field._box._search_box.setText("Cliente B")
    assert field.value() is None
    field._box.selected.emit(SearchOption(id="B", label="Cliente B"))
    assert field.value() == "B"
    assert field._box._search_box.text() == "Cliente B"


def test_clearing_the_text_clears_the_selection(app):
    field = _field()
    field.set_value("A", "Cliente A")
    assert field.value() == "A"
    field._box._search_box.clear()
    assert field.value() is None


def test_required_customer_blocks_saving_after_editing_text(app):
    saved = []
    dialog = CrmFormDialog(title="x", fields=(FieldSpec("customer", "Cliente", "customer",
                                                         required=True),),
                           on_submit=lambda v: saved.append(v) or None)
    widget = dialog.input("customer")
    widget._box.selected.emit(SearchOption(id="A", label="Cliente A"))
    widget._box._search_box.setText("Otro")
    dialog._submit()
    assert saved == []
