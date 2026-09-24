"""Cero resultados debe decir POR QUÉ, y ningún buscador puede nacer sin proveedor.

Dos defectos distintos que se veían igual en pantalla:

1. Con habilitación por sucursal deliberada, "no aparece el producto" es el caso
   normal. Presentarlo como "Sin resultados" —idéntico a "no existe"— hace que se
   lea como un buscador roto. Los widgets aceptan ahora un `empty_reason_provider`
   opcional que explica la causa real.
2. `AddCartLineDialog` (Compra Directa) y `OrderFormDialog` (Órdenes) se
   construían SIN `product_provider`, así que caían al `lambda _q: []` por
   omisión y devolvían cero siempre, hubiera o no catálogo. El guard por AST de
   abajo cubre la clase entera, no sólo esos dos.
"""

import ast
import os
import pathlib
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = pathlib.Path(__file__).resolve().parents[2]


def _qt_components():
    qt_core = pytest.importorskip(
        "PyQt5.QtCore", reason="PyQt5 requerido", exc_type=ImportError)
    qt_widgets = pytest.importorskip(
        "PyQt5.QtWidgets", reason="PyQt5 requerido", exc_type=ImportError)
    from frontend.desktop import components

    application = qt_widgets.QApplication.instance() or qt_widgets.QApplication(sys.argv)
    return qt_core, components, application


_RAZON = "Hay productos, pero ninguno está habilitado en esta sucursal."


# ── SearchSelector ────────────────────────────────────────────────────────
def test_selector_muestra_la_causa_en_vez_del_generico():
    _qt, components, _app = _qt_components()
    selector = components.SearchSelector(
        provider=lambda _q: [], empty_reason_provider=lambda _q: _RAZON)

    selector.refresh("pollo")

    assert selector._results.count() == 1
    assert selector._results.item(0).text() == _RAZON
    assert selector.has_search_failed() is False


def test_selector_cae_al_generico_si_no_hay_causa():
    _qt, components, _app = _qt_components()
    selector = components.SearchSelector(
        provider=lambda _q: [], empty_reason_provider=lambda _q: None)

    selector.refresh("pollo")

    assert selector._results.item(0).text() == components.NO_RESULTS_MESSAGE


def test_una_causa_que_revienta_no_rompe_el_buscador():
    """El diagnóstico es accesorio: si falla, mensaje genérico, nunca excepción."""
    _qt, components, _app = _qt_components()

    def _truena(_q):
        raise RuntimeError("boom")

    selector = components.SearchSelector(
        provider=lambda _q: [], empty_reason_provider=_truena)

    selector.refresh("pollo")

    assert selector._results.item(0).text() == components.NO_RESULTS_MESSAGE
    assert selector.has_search_failed() is False


def test_un_fallo_de_busqueda_sigue_ganando_sobre_la_causa():
    """§35: si la consulta falló, eso es lo que hay que decir — no una causa
    de "por qué no hay resultados", porque no llegó a haber consulta."""
    _qt, components, _app = _qt_components()

    def _provider_que_truena(_q):
        raise RuntimeError("boom")

    selector = components.SearchSelector(
        provider=_provider_que_truena, empty_reason_provider=lambda _q: _RAZON)

    selector.refresh("pollo")

    assert selector.has_search_failed() is True
    assert selector._results.item(0).text() == components.SEARCH_FAILED_MESSAGE


def test_product_search_box_reenvia_la_causa():
    _qt, components, _app = _qt_components()
    caja = components.ProductSearchBox(
        provider=lambda _q: [], empty_reason_provider=lambda _q: _RAZON)

    caja.refresh("pollo")

    assert caja._results.item(0).text() == _RAZON


# ── EntitySearchInput ─────────────────────────────────────────────────────
def test_entity_search_input_muestra_la_causa():
    _qt, components, _app = _qt_components()
    entrada = components.EntitySearchInput(
        provider=lambda _q: [], empty_reason_provider=lambda _q: _RAZON)

    entrada._run_search("pollo")

    assert entrada._results.item(0).text() == _RAZON
    assert entrada.has_search_failed() is False


def test_entity_search_input_cae_al_generico():
    _qt, components, _app = _qt_components()
    entrada = components.EntitySearchInput(provider=lambda _q: [])

    entrada._run_search("pollo")

    assert entrada._results.item(0).text() == components.NO_RESULTS_MESSAGE


# ── ningún buscador de productos sin proveedor (AST) ──────────────────────
#: Diálogos cuyo buscador de productos queda inservible si se construyen sin
#: `product_provider` (caen al proveedor vacío por omisión).
_DIALOGOS_CON_BUSCADOR = {
    "AddCartLineDialog", "OrderFormDialog", "RequisitionFormDialog",
    "QuoteCaptureDialog", "InvoiceFormDialog",
}

#: Se barre el módulo COMPLETO, no una lista elegida a mano: el defecto
#: apareció justamente en un sitio que nadie estaba mirando, y una lista fija
#: se queda corta en cuanto alguien añade otra pantalla.
_MODULO_COMPRAS = "frontend/desktop/modules/purchasing"


def _construcciones_sin_proveedor(path: pathlib.Path) -> list[str]:
    arbol = ast.parse(path.read_text(encoding="utf-8"))
    faltantes = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        nombre = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
        if nombre not in _DIALOGOS_CON_BUSCADOR:
            continue
        if not any(kw.arg == "product_provider" for kw in nodo.keywords):
            faltantes.append(f"{path.name}:{nodo.lineno} {nombre}")
    return faltantes


def test_ningun_dialogo_de_compras_nace_sin_proveedor_de_productos():
    archivos = sorted((REPO / _MODULO_COMPRAS).rglob("*.py"))
    assert archivos, "No se encontró el módulo de Compras"
    faltantes = []
    for ruta in archivos:
        faltantes += _construcciones_sin_proveedor(ruta)
    assert not faltantes, (
        "Buscador de productos sin proveedor (devolvería cero siempre): "
        + ", ".join(faltantes))
