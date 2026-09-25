"""«Nueva orden» usa la búsqueda ESTÁNDAR de productos (`ProductSearchQuery`,
`ProductSearchBox`), como Mermas, Inventario y Compras:

- sólo productos habilitados en la sucursal activa (la habilitación es
  deliberada) y, si no hay resultados, dice POR QUÉ;
- el preset depende del proceso: formular busca lo que se FABRICA
  (producibles); despiezar, empacar o acondicionar buscan la ENTRADA
  (insumos de producción).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.application.meat_processing.queries import ProcessingOrderQueryService
from backend.shared.ids import new_uuid
from frontend.desktop.modules.meat_processing.presenters.processing_order_presenter import (
    ProcessingOrderPresenter,
)
from tests.integration.meat_processing._generic_plant import Planta, build_db


class _Sesion:
    def __init__(self, branch):
        self.active_branch_id = branch
        self.user_id = new_uuid()


def _habilitar(conn, producto, branch):
    conn.execute("INSERT INTO branch_product (id, product_id, branch_id, enabled)"
                 " VALUES (?,?,?,1)", (new_uuid(), producto, branch))
    conn.commit()


@pytest.fixture()
def planta():
    conn = build_db()
    p = Planta(conn)
    p.canal = p.producto("Canal bovina")
    p.mezcla = p.producto("Mezcla para hamburguesa")
    conn.execute("UPDATE products SET producible=0 WHERE id=?", (p.canal,))
    conn.execute("UPDATE products SET inventory_managed=0 WHERE id=?", (p.mezcla,))
    conn.commit()
    p.presentador = ProcessingOrderPresenter(
        connection_provider=lambda: conn, query_factory=ProcessingOrderQueryService,
        session_context=_Sesion(p.branch))
    yield p
    conn.close()


def _nombres(opciones):
    return [o.label for o in opciones]


def test_only_products_enabled_in_the_branch_are_offered(planta):
    assert planta.presentador.product_options("canal", "CUTTING") == []
    _habilitar(planta.conn, planta.canal, planta.branch)
    assert _nombres(planta.presentador.product_options("canal", "CUTTING")) == ["Canal bovina"]


def test_an_empty_search_explains_why(planta):
    razon = planta.presentador.product_search_reason("canal", "CUTTING")
    assert razon and "sucursal" in razon.lower()


def test_a_cutting_looks_for_its_input_and_a_formulation_for_what_it_makes(planta):
    for producto in (planta.canal, planta.mezcla):
        _habilitar(planta.conn, producto, planta.branch)
    # Despiece: la entrada (insumo de producción inventariable).
    assert _nombres(planta.presentador.product_options("", "CUTTING")) == ["Canal bovina"]
    # Formulación: lo que se fabrica (producible).
    assert _nombres(planta.presentador.product_options("", "MIXING")) == [
        "Mezcla para hamburguesa"]


@pytest.fixture(scope="module")
def app():
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_the_dialog_uses_the_standard_search_box_and_follows_the_process(app, planta):
    from frontend.desktop.components.product_search_box import ProductSearchBox
    from frontend.desktop.modules.meat_processing.dialogs import CreateProcessingOrderDialog

    pedidos = []

    def proveedor(query, proceso):
        pedidos.append(proceso)
        return []

    dlg = CreateProcessingOrderDialog(
        process_types=[("CUTTING", "Corte"), ("MIXING", "Mezclado")],
        product_provider=proveedor,
        empty_reason_provider=lambda q, proceso: f"sin {proceso}")
    assert isinstance(dlg.product, ProductSearchBox)
    dlg.process_type_combo.setCurrentIndex(1)
    dlg.product.refresh("x")
    assert pedidos[-1] == "MIXING"
    assert dlg.product_id() is None
