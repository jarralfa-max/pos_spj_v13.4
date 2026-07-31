"""P1-C slice 10 — el form de despiece usa selectores canónicos: especie por
catálogo (no UUID a mano) y producto/unidad por catálogo (§18). Cierra el
escenario 5 para despieces.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.components import EntitySearchInput, SearchableComboBox  # noqa: E402
from frontend.desktop.modules.products.dialogs.cutting_form_dialog import (  # noqa: E402
    CuttingSchemeFormDialog,
    _OutputEditor,
)


class _FakePresenter:
    def __init__(self):
        self.created = None

    def list_species(self):
        return [{"id": "sp-ave", "code": "AVE", "label": "Ave — pollo"},
                {"id": "sp-bov", "code": "BOV", "label": "Bovino"}]

    def search_products_for_assignment(self, query=None):
        return [{"id": "p-pechuga", "code": "C2", "name": "Pechuga"}]

    def list_units(self):
        return [{"id": "u-kg", "code": "KG", "name": "Kilogramo"}]

    def create_cutting_scheme(self, *, input_product_id, species_id, name, cut_level,
                              outputs):
        self.created = dict(input_product_id=input_product_id, species_id=species_id,
                            name=name, cut_level=cut_level, outputs=outputs)
        return True, "OK"


@pytest.fixture(autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


def test_species_and_output_use_selectors():
    dlg = CuttingSchemeFormDialog(_FakePresenter(), input_product_id="p-canal")
    assert isinstance(dlg.species, SearchableComboBox)
    # el catálogo de especies pobló el combo (placeholder + 2)
    assert dlg.species.count() == 3
    ed = _OutputEditor(_FakePresenter())
    assert isinstance(ed.product, EntitySearchInput)
    assert isinstance(ed.unit, SearchableComboBox)


def test_preset_species_kept_even_if_not_in_catalog():
    dlg = CuttingSchemeFormDialog(_FakePresenter(), input_product_id="p-canal",
                                  species_id="sp-desconocida")
    assert dlg.species.current_id() == "sp-desconocida"


def test_save_uses_selected_species():
    presenter = _FakePresenter()
    dlg = CuttingSchemeFormDialog(presenter, input_product_id="p-canal")
    dlg.name.setText("Despiece pollo")
    dlg.species.set_current_id("sp-ave")
    dlg.cut_level.setCurrentIndex(dlg.cut_level.findData("PRIMARY"))
    dlg._outputs = [{"product_id": "p-pechuga", "output_type": "MAIN_PRODUCT",
                    "measure_kind": "BY_WEIGHT", "quantity": "0.3", "unit_id": "u-kg"}]
    dlg._on_save()
    assert presenter.created is not None
    assert presenter.created["species_id"] == "sp-ave"
    assert presenter.created["cut_level"] == "PRIMARY"
