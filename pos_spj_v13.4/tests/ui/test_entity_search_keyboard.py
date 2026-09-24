"""`EntitySearchInput` se maneja con teclado y nunca cierra el diálogo.

Reproducido el 2026-09-18 en "Nueva solicitud de compra": el buscador sólo
elegía con CLIC, y dentro de un diálogo Enter activaba "Aceptar" — escribir un
producto y pulsar Enter cerraba el diálogo sin líneas. El componente lo usan 14
pantallas de 7 módulos (Compras, Inventario, Productos, Precios, Cárnico,
Transferencias…), así que el arreglo y estas pruebas valen para todas.
"""

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialog, QDialogButtonBox, QVBoxLayout

from frontend.desktop.components.entity_search_input import EntitySearchInput
from frontend.desktop.components.search_selector import SearchOption


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


_OPCIONES = [SearchOption(id="p1", label="Pollo Entero"),
             SearchOption(id="p2", label="Pollo Marinado")]


def _buscador(parent=None, opciones=_OPCIONES):
    return EntitySearchInput(parent, provider=lambda q: [o for o in opciones
                                                         if q.lower() in o.label.lower()],
                             debounce_ms=0)


def _escribir(w, texto):
    QTest.keyClicks(w._search, texto)
    w._run_search(w._search.text())


class TestKeyboard:
    def test_enter_chooses_the_highlighted_result(self, app):
        w = _buscador()
        _escribir(w, "Pollo")
        QTest.keyClick(w._search, Qt.Key_Return)
        assert w.selected_id() == "p1"

    def test_the_first_result_is_highlighted_so_you_see_what_enter_picks(self, app):
        w = _buscador()
        _escribir(w, "Pollo")
        assert w._results.currentRow() == 0

    def test_arrows_move_the_highlight(self, app):
        w = _buscador()
        _escribir(w, "Pollo")
        QTest.keyClick(w._search, Qt.Key_Down)
        QTest.keyClick(w._search, Qt.Key_Return)
        assert w.selected_id() == "p2"

    def test_enter_before_the_debounce_runs_the_search_now(self, app):
        w = EntitySearchInput(provider=lambda q: _OPCIONES[:1], debounce_ms=10_000)
        QTest.keyClicks(w._search, "Pollo")          # la espera aún no vence
        QTest.keyClick(w._search, Qt.Key_Return)
        assert w.selected_id() == "p1"

    def test_a_status_row_is_never_chosen(self, app):
        w = _buscador(opciones=[])
        _escribir(w, "Nada")
        QTest.keyClick(w._search, Qt.Key_Return)
        assert w.selected_id() is None


class TestInsideADialog:
    def test_enter_never_accepts_the_dialog(self, app):
        """EL FALLO REPORTADO."""
        d = QDialog()
        lay = QVBoxLayout(d)
        w = _buscador(d)
        lay.addWidget(w)
        caja = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, d)
        caja.button(QDialogButtonBox.Ok).setDefault(True)
        caja.accepted.connect(d.accept)
        lay.addWidget(caja)
        aceptado = []
        d.accepted.connect(lambda: aceptado.append(1))
        d.show()
        _escribir(w, "Pollo")
        QTest.keyClick(w._search, Qt.Key_Return)
        QTest.keyClick(w._search, Qt.Key_Return)     # también con algo ya elegido
        assert aceptado == []
        d.close()


class TestStaleSelection:
    def test_editing_after_choosing_clears_the_selection(self, app):
        """Si no, el texto decía una cosa y `selected_id()` devolvía otra, y
        "Agregar" añadía el producto anterior."""
        w = _buscador()
        _escribir(w, "Pollo")
        QTest.keyClick(w._search, Qt.Key_Return)
        assert w.selected_id() == "p1"
        QTest.keyClicks(w._search, "x")
        assert w.selected_id() is None

    def test_programmatic_selection_is_kept(self, app):
        """`set_selected_label` (precarga al editar) no cuenta como edición."""
        w = _buscador()
        w.set_selected_label("p2", "Pollo Marinado")
        assert w.selected_id() == "p2"
