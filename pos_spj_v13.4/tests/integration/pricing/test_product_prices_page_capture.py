"""La pantalla de Precios por producto ante listas de solo lectura.

Antes: sin listas editables decía "No hay listas editables: crea una, o usa una
en borrador o en revisión" —sin mencionar que la lista activa existe ni cómo
partir de ella— y al editar un precio de una lista activa sólo se negaba.
Ahora explica, ofrece duplicar y abre el precio ya sobre la copia en borrador.
"""

from __future__ import annotations

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from backend.application.pricing.permissions import PricingPermissions
from frontend.desktop.modules.pricing.dialogs.pricing_dialogs import (
    BulkPriceDialog,
    DuplicatePriceListDialog,
)
from frontend.desktop.modules.pricing.pages import product_prices_page as pagina_mod
from frontend.desktop.modules.pricing.presenter import PricingPresenter
from frontend.desktop.modules.pricing.view_models import ListCaptureState, TableViewModel


@pytest.fixture(scope="module")
def app():
    # A nivel de módulo: crear la QApplication dentro del cuerpo de un test
    # tumba pytest en silencio en este entorno.
    return QApplication.instance() or QApplication([])


class _PresentadorFalso:
    """Lo mínimo que usa la página; los mensajes son los REALES del presentador."""

    def __init__(self, *, state, permisos=("*",), detalle=None, resumen=None):
        self._state = state
        self._permisos = set(permisos)
        self._detalle = detalle
        self._resumen = resumen or {}
        self.duplicados = []
        self.guardados = []

    def can(self, code):
        return "*" in self._permisos or code in self._permisos

    def product_prices(self, *, query=None):
        return TableViewModel()

    def price_list_capture_state(self):
        return self._state

    def price_list_options(self):
        return list(self._state.editable)

    def no_editable_lists_message(self, state=None):
        return PricingPresenter.no_editable_lists_message(self, state or self._state)

    read_only_list_message = staticmethod(PricingPresenter.read_only_list_message)

    def price_details(self, _price_id):
        return self._detalle

    def price_list_summary(self, list_id):
        return self._resumen.get(list_id)

    def suggest_copy_code(self, code):
        return f"{code}-2"

    def duplicate_price_list(self, **fields):
        self.duplicados.append(fields)
        return True, "Lista creada en Borrador", {"entity_id": "copia-1"}

    def branch_options(self):
        return [("", "Todas las sucursales")]

    def set_product_price(self, **fields):
        self.guardados.append(fields)
        return True, "Precio actualizado", {}


_ACTIVA = {"id": "l-act", "label": "BASE01 · Lista base", "status": "ACTIVE",
           "price_count": 0}


@pytest.fixture
def mensajes(monkeypatch):
    vistos = {"warning": [], "question": [], "information": []}

    def _registrar(tipo, respuesta=None):
        def _fn(_parent, _title, text, *args, **kwargs):
            vistos[tipo].append(text)
            return respuesta
        return _fn

    monkeypatch.setattr(QMessageBox, "warning", _registrar("warning"))
    monkeypatch.setattr(QMessageBox, "information", _registrar("information"))
    monkeypatch.setattr(QMessageBox, "question", _registrar("question", QMessageBox.No))
    return vistos


def test_sin_listas_editables_explica_y_ofrece_duplicar_la_activa(app, mensajes):
    p = _PresentadorFalso(state=ListCaptureState(read_only=(_ACTIVA,)))
    page = pagina_mod.ProductPricesPage(p)

    page._create()

    assert mensajes["question"], "debía ofrecer duplicar"
    texto = mensajes["question"][0]
    assert "BASE01 · Lista base (Activa)" in texto and "solo lectura" in texto
    assert "¿Duplicar ahora «BASE01 · Lista base»?" in texto
    assert p.duplicados == []          # respondió No: no se duplica nada


def test_sin_permiso_para_crear_listas_solo_explica(app, mensajes):
    p = _PresentadorFalso(state=ListCaptureState(read_only=(_ACTIVA,)),
                          permisos=(PricingPermissions.PRICE_CREATE,))
    pagina_mod.ProductPricesPage(p)._create()
    assert not mensajes["question"]
    assert "duplícala" in mensajes["warning"][0]


def test_editar_precio_de_lista_activa_ofrece_duplicar_y_abre_la_copia(
        app, mensajes, monkeypatch):
    detalle = {"id": "pp-1", "price_list_id": "l-act", "list_status": "ACTIVE",
               "list_code": "BASE01", "list_name": "Lista base", "product_id": "p1",
               "product_name": "Arrachera", "branch_id": "", "sale_price": "100"}
    p = _PresentadorFalso(state=ListCaptureState(editable=(("copia-1", "BASE01-2"),)),
                          detalle=detalle,
                          resumen={"l-act": {"status_recognized": True}})
    page = pagina_mod.ProductPricesPage(p)
    monkeypatch.setattr(page.table, "selected_row_id", lambda: "pp-1")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: mensajes["question"].append(a[2]) or QMessageBox.Yes)
    abiertos = []
    monkeypatch.setattr(pagina_mod.DuplicatePriceListDialog, "exec_", lambda self: True)

    def _abrir_precio(self):
        abiertos.append(self.values())
        return True
    monkeypatch.setattr(pagina_mod.ProductPriceFormDialog, "exec_", _abrir_precio)

    page._edit()

    assert "está Activa y es de solo lectura" in mensajes["question"][0]
    assert p.duplicados[0]["source_list_id"] == "l-act"
    assert p.duplicados[0]["code"] == "BASE01-2"
    # El precio se abre sobre la COPIA, con el producto ya elegido.
    assert abiertos and abiertos[0]["price_list_id"] == "copia-1"
    assert abiertos[0]["product_id"] == "p1"
    assert p.guardados[0]["price_list_id"] == "copia-1"


def test_estado_no_reconocido_no_ofrece_duplicar(app, mensajes, monkeypatch):
    detalle = {"id": "pp-1", "price_list_id": "l-rara", "list_status": "publicada",
               "list_name": "Rara"}
    p = _PresentadorFalso(state=ListCaptureState(), detalle=detalle,
                          resumen={"l-rara": {"status_recognized": False}})
    page = pagina_mod.ProductPricesPage(p)
    monkeypatch.setattr(page.table, "selected_row_id", lambda: "pp-1")

    page._edit()

    assert not mensajes["question"]
    assert "no reconocido" in mensajes["warning"][0] and "«publicada»" in mensajes["warning"][0]


def test_dialogo_de_duplicar_precarga_codigo_y_nombre(app):
    d = DuplicatePriceListDialog(source_label="BASE01 · Base", initial_code="BASE01-2",
                                 initial_name="Base (copia)")
    assert d.values() == {"code": "BASE01-2", "name": "Base (copia)",
                          "copy_prices": True}


def test_el_lote_entrega_la_vigencia_solo_si_se_programa(app):
    d = BulkPriceDialog(list_options=[("l1", "L1")], category_options=[("c1", "C1")])
    assert "effective_from" not in d.values()
    d._scheduled.setChecked(True)
    assert {"effective_from", "effective_to"} <= set(d.values())
