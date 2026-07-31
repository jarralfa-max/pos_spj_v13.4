"""P1-C slice 8 — el form de recetas usa selectores canónicos (no UUID a mano) y
captura outputs (§15). Cierra el escenario 5 para recetas.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLineEdit  # noqa: E402

from frontend.desktop.components import (  # noqa: E402
    EntitySearchInput,
    SearchableComboBox,
)
from frontend.desktop.modules.products.dialogs.recipe_form_dialog import (  # noqa: E402
    RecipeFormDialog,
    _ComponentEditor,
    _OutputEditor,
)


class _FakePresenter:
    def __init__(self):
        self.created = None

    def search_products_for_assignment(self, query=None):
        return [{"id": "p-pollo", "code": "C1", "name": "Pollo"},
                {"id": "p-pechuga", "code": "C2", "name": "Pechuga"}]

    def list_units(self):
        return [{"id": "u-kg", "code": "KG", "name": "Kilogramo"}]

    def create_recipe(self, *, product_id, recipe_type, name, components, outputs):
        self.created = dict(product_id=product_id, recipe_type=recipe_type, name=name,
                            components=components, outputs=outputs)
        return True, "OK"


@pytest.fixture(autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


def test_component_editor_uses_selectors_not_uuid_lineedit():
    ed = _ComponentEditor(_FakePresenter())
    assert isinstance(ed.product, EntitySearchInput)
    assert isinstance(ed.unit, SearchableComboBox)
    # no hay QLineEdit para producto/unidad (sólo el buscador interno de texto)
    assert not isinstance(ed.product, QLineEdit)


def test_component_editor_value_from_selection():
    ed = _ComponentEditor(_FakePresenter())
    ed._labels["p-pollo"] = "Pollo"
    ed.product.set_selected_label("p-pollo", "Pollo")
    ed.quantity.set_decimal("2.5")
    ed.unit.set_current_id("u-kg")
    v = ed.value()
    assert v == {"component_product_id": "p-pollo", "product_label": "Pollo",
                 "quantity": "2.500", "unit_id": "u-kg", "unit_label": "KG — Kilogramo"}


def test_output_editor_captures_type_and_pct():
    ed = _OutputEditor(_FakePresenter())
    ed._labels["p-pechuga"] = "Pechuga"
    ed.product.set_selected_label("p-pechuga", "Pechuga")
    ed.output_type.setCurrentIndex(ed.output_type.findData("BY_PRODUCT"))
    ed.quantity.set_decimal("0.3")
    ed.unit.set_current_id("u-kg")
    ed.pct.setValue(30.0)
    v = ed.value()
    assert v["product_id"] == "p-pechuga" and v["output_type"] == "BY_PRODUCT"
    assert v["quantity"] == "0.300" and v["unit_id"] == "u-kg"
    assert v["expected_yield_pct"] == "30.0"


def test_save_passes_components_and_outputs():
    presenter = _FakePresenter()
    dlg = RecipeFormDialog(presenter, product_id="p-canal")
    dlg.name.setText("Despiece pollo")
    dlg._components = [{"component_product_id": "p-pollo", "quantity": "1",
                       "unit_id": "u-kg"}]
    dlg._outputs = [{"product_id": "p-pechuga", "output_type": "MAIN_PRODUCT",
                    "quantity": "0.3", "unit_id": "u-kg", "expected_yield_pct": "30"}]
    dlg._on_save()
    assert presenter.created is not None
    assert presenter.created["product_id"] == "p-canal"
    assert len(presenter.created["components"]) == 1
    assert len(presenter.created["outputs"]) == 1
    assert presenter.created["outputs"][0]["output_type"] == "MAIN_PRODUCT"
