"""P1-C slice 9 — el form de rendimientos usa selectores canónicos, muestra el
total/tolerancia/estado en vivo y simula (§16). Cierra el escenario 5 para yields.
"""

import os
from decimal import Decimal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.components import EntitySearchInput, SearchableComboBox  # noqa: E402
from frontend.desktop.modules.products.dialogs.yield_form_dialog import (  # noqa: E402
    YieldProfileFormDialog,
    _OutputEditor,
)


class _FakePresenter:
    def __init__(self):
        self.created = None

    def search_products_for_assignment(self, query=None):
        return [{"id": "p-pechuga", "code": "C2", "name": "Pechuga"}]

    def list_units(self):
        return [{"id": "u-kg", "code": "KG", "name": "Kilogramo"}]

    def create_yield_profile(self, *, input_product_id, name, tolerance_pct, outputs):
        self.created = dict(input_product_id=input_product_id, name=name,
                            tolerance_pct=tolerance_pct, outputs=outputs)
        return True, "OK"


@pytest.fixture(autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


def test_output_editor_uses_selectors():
    ed = _OutputEditor(_FakePresenter())
    assert isinstance(ed.product, EntitySearchInput)
    assert isinstance(ed.unit, SearchableComboBox)


def test_live_total_and_status_within_tolerance():
    dlg = YieldProfileFormDialog(_FakePresenter(), input_product_id="p-canal")
    dlg.tolerance.setValue(2.0)
    dlg._outputs = [{"expected_yield_pct": "30"}, {"expected_yield_pct": "35"},
                    {"expected_yield_pct": "33"}]  # total 98 → dentro de ±2
    dlg._refresh_total()
    assert dlg.total_expected() == Decimal("98")
    assert dlg.status()[0] == "Válido"
    assert "Total esperado: 98.00 %" in dlg._total_label.text()


def test_live_status_out_of_tolerance():
    dlg = YieldProfileFormDialog(_FakePresenter(), input_product_id="p-canal")
    dlg.tolerance.setValue(2.0)
    dlg._outputs = [{"expected_yield_pct": "104"}]  # exceso 4 > ±2
    dlg._refresh_total()
    estado, delta = dlg.status()
    assert estado == "Fuera de tolerancia" and "Exceso: 4.00 %" in delta


def test_simulation_is_informative():
    dlg = YieldProfileFormDialog(_FakePresenter(), input_product_id="p-canal")
    dlg._outputs = [{"product_label": "Pechuga", "expected_yield_pct": "30"}]
    dlg.sim_input.set_decimal("52.4")
    dlg._simulate()
    # 52.4 * 30% = 15.720
    assert "Pechuga: 15.720" in dlg.sim_result.text()


def test_save_passes_outputs_with_min_max():
    presenter = _FakePresenter()
    dlg = YieldProfileFormDialog(presenter, input_product_id="p-canal")
    dlg.name.setText("Rendimiento pollo")
    dlg.tolerance.setValue(2.0)
    dlg._outputs = [{"product_id": "p-pechuga", "output_type": "MAIN_PRODUCT",
                    "expected_yield_pct": "30", "unit_id": "u-kg",
                    "minimum_yield_pct": "28", "maximum_yield_pct": "32"}]
    dlg._on_save()
    assert presenter.created is not None
    assert Decimal(presenter.created["tolerance_pct"]) == Decimal("2")
    assert presenter.created["outputs"][0]["minimum_yield_pct"] == "28"
