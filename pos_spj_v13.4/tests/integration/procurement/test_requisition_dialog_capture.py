""""No permite crear nueva solicitud" — los escenarios reproducidos, como pruebas.

Reproducido el 2026-09-18 simulando teclado y ratón reales sobre el diálogo que
arma la app, con la sesión real de un usuario real:

A) escribir el producto y pulsar Enter CERRABA el diálogo sin líneas;
B) escribir el producto sin hacer clic en el resultado: "Agregar" no hacía nada
   y no avisaba;
C) "Aceptar" sin líneas cerraba el diálogo y el aviso llegaba DESPUÉS, con todo
   lo capturado ya perdido.

El backend creaba la solicitud sin problema: el fallo era sólo de pantalla.
"""

import sqlite3

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton

from frontend.desktop.components.search_selector import SearchOption
from frontend.desktop.modules.purchasing.dialogs.enterprise_dialogs import (
    OrderFormDialog,
    RequisitionFormDialog,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def avisos(monkeypatch):
    """`QMessageBox.warning` es modal: bloquearía la prueba."""
    capturados = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: capturados.append(a[2])))
    return capturados


def _productos(q):
    return [o for o in (SearchOption(id="p1", label="Pollo Entero"),)
            if q.lower() in o.label.lower()]


def _dialogo():
    d = RequisitionFormDialog(product_provider=_productos,
                              branch_options=[("br-1", "Corregidora")], branch_id="br-1")
    d._lines._product._search.set_debounce_ms(0)
    aceptado = []
    d.accepted.connect(lambda: aceptado.append(1))
    d.show()
    return d, aceptado


def _escribir_producto(d, texto="Pollo"):
    buscador = d._lines._product._search
    QTest.keyClicks(buscador, texto)
    d._lines._product._run_search(buscador.text())
    return buscador


def _agregar(d):
    return [b for b in d._lines.findChildren(QPushButton) if b.text() == "Agregar"][0]


class TestTheReportedScenarios:
    def test_a_enter_in_the_product_search_chooses_it_and_keeps_the_dialog(self, app, avisos):
        d, aceptado = _dialogo()
        buscador = _escribir_producto(d)
        QTest.keyClick(buscador, Qt.Key_Return)
        assert aceptado == []
        assert d._lines._product.selected_id() == "p1"
        d.close()

    def test_a_enter_in_quantity_adds_the_line(self, app, avisos):
        d, aceptado = _dialogo()
        QTest.keyClick(_escribir_producto(d), Qt.Key_Return)
        QTest.keyClicks(d._lines._qty, "10")
        QTest.keyClick(d._lines._qty, Qt.Key_Return)
        assert aceptado == []
        assert [ln["product_id"] for ln in d._lines.lines()] == ["p1"]
        d.close()

    def test_b_add_without_choosing_explains_why(self, app, avisos):
        d, _ = _dialogo()
        _escribir_producto(d)
        QTest.keyClicks(d._lines._qty, "10")
        QTest.mouseClick(_agregar(d), Qt.LeftButton)
        assert d._lines.lines() == []
        assert "Elige el producto" in d._lines._status.text()
        d.close()

    def test_b_add_without_quantity_explains_why(self, app, avisos):
        d, _ = _dialogo()
        QTest.keyClick(_escribir_producto(d), Qt.Key_Return)
        QTest.mouseClick(_agregar(d), Qt.LeftButton)
        assert "cantidad" in d._lines._status.text()
        d.close()

    def test_c_accept_without_lines_stays_open(self, app, avisos):
        d, aceptado = _dialogo()
        d.accept()
        assert aceptado == [] and avisos == ["Agrega al menos un producto."]
        d.close()

    def test_c_accept_with_a_captured_but_unadded_product_warns(self, app, avisos):
        """El caso más probable de perder la captura: todo escrito, sin
        pulsar "Agregar"."""
        d, aceptado = _dialogo()
        QTest.keyClick(_escribir_producto(d), Qt.Key_Return)
        QTest.keyClicks(d._lines._qty, "10")
        d.accept()
        assert aceptado == [] and "sin agregar" in avisos[-1]
        d.close()

    def test_the_whole_flow_works_with_the_keyboard_only(self, app, avisos):
        d, aceptado = _dialogo()
        QTest.keyClick(_escribir_producto(d), Qt.Key_Return)
        QTest.keyClicks(d._lines._qty, "10")
        QTest.keyClick(d._lines._qty, Qt.Key_Return)
        d.accept()
        assert aceptado == [1]
        assert d.values()["lines"] == [
            {"product_id": "p1", "description": "Pollo Entero", "quantity": "10.000",
             "purchase_nature": "INVENTORY"}]
        d.close()


class TestTheOrderDialog:
    def test_zero_price_is_refused_on_screen(self, app, avisos):
        """Decisión del usuario: el costo debe ser mayor a cero."""
        d = OrderFormDialog(supplier_provider=lambda q: [],
                            product_provider=_productos,
                            branch_options=[("br-1", "Corregidora")], branch_id="br-1",
                            warehouse_options=[("wh-1", "Almacén")], warehouse_id="wh-1")
        d._lines._product._search.set_debounce_ms(0)
        QTest.keyClick(_escribir_producto(d), Qt.Key_Return)
        QTest.keyClicks(d._lines._qty, "5")
        QTest.keyClicks(d._lines._price, "0")
        QTest.mouseClick(_agregar(d), Qt.LeftButton)
        assert d._lines.lines() == []
        assert "precio mayor a cero" in d._lines._status.text()
        d.close()

    def test_accept_requires_supplier_warehouse_and_lines(self, app, avisos):
        d = OrderFormDialog(supplier_provider=lambda q: [], product_provider=_productos,
                            branch_options=[("br-1", "Corregidora")], branch_id="br-1",
                            warehouse_options=[("wh-1", "Almacén")])
        aceptado = []
        d.accepted.connect(lambda: aceptado.append(1))
        d.accept()
        # El aviso vive DENTRO del diálogo (banner), no en un QMessageBox aparte.
        assert aceptado == [] and "proveedor" in d.error_text()
        d.close()
