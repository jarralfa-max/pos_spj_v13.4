"""Fase 10 (2026-09-19) — la pantalla que ejecuta una orden de despiece.

- La captura propone lo ESPERADO del despiece y no deja ejecutar sin pesos.
- Si falta existencia o un corte sale fuera de tolerancia, se pide la
  autorización de otro usuario (usuario, clave, motivo) y se REINTENTA: el
  caso de uso es reanudable, así que reintentar continúa, no duplica.
- Las casillas de uso de Almacenes llegan hasta el presenter (sin ellas,
  Cárnico no tiene dónde producir).
"""
from __future__ import annotations

import os
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _salida(pid, tipo, esperado):
    return SimpleNamespace(product_id=pid, output_type=tipo, product_name=pid.title(),
                           expected_weight=Decimal(esperado), per_unit=Decimal("0"))


PLAN = {"order_id": "o1", "status": "RELEASED", "input_product_id": "pollo",
        "input_product_name": "Pollo entero", "planned_weight": Decimal("10"),
        "has_despiece": True,
        "outputs": [_salida("pechuga", "MAIN_PRODUCT", "3.5"),
                    _salida("merma", "WASTE", "0.5")]}


class _Presentador:
    """Presenter de mentira: registra lo que la pantalla le pide."""

    def __init__(self, respuestas, *, autorizador=("gerente-id", "")):
        self.respuestas = list(respuestas)
        self.autorizador = autorizador
        self.llamadas = []

    def execution_plan(self, order_id):
        return PLAN

    def execute_order(self, **kwargs):
        self.llamadas.append(kwargs)
        return self.respuestas.pop(0)

    def verify_authorizer(self, usuario, clave):
        return self.autorizador

    def orders(self):
        return SimpleNamespace(rows=[], row_ids=[])


class TestCapturaDeEjecucion:
    def test_propone_lo_esperado_del_despiece(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecuteProcessingOrderDialog,
        )

        dlg = ExecuteProcessingOrderDialog(plan=PLAN)
        assert dlg.input_weight_value() == Decimal("10")
        pesos = {o["product_id"]: o["weight"] for o in dlg.outputs()}
        assert pesos["pechuga"] == Decimal("3.5") and pesos["merma"] == Decimal("0.5")

    def test_no_ejecuta_sin_peso_de_entrada(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecuteProcessingOrderDialog,
        )

        dlg = ExecuteProcessingOrderDialog(plan=PLAN)
        dlg.input_weight.set_decimal(Decimal("0"))
        dlg._accept_if_valid()
        assert dlg.result() != QtWidgets.QDialog.Accepted

    def test_no_ejecuta_sin_peso_de_ningun_corte(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecuteProcessingOrderDialog,
        )

        dlg = ExecuteProcessingOrderDialog(plan=PLAN)
        for campo in dlg._campos.values():
            campo.set_decimal(Decimal("0"))
        dlg._accept_if_valid()
        assert dlg.result() != QtWidgets.QDialog.Accepted


class TestAutorizacionDeProduccion:
    def test_exige_motivo(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ProductionAuthorizationDialog,
        )

        dlg = ProductionAuthorizationDialog(message="falta existencia",
                                            presenter=_Presentador([]))
        dlg._authorize()
        assert dlg.authorizer_user_id is None

    def test_clave_incorrecta_no_autoriza(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ProductionAuthorizationDialog,
        )

        presentador = _Presentador([], autorizador=(None, "Usuario o clave incorrectos"))
        dlg = ProductionAuthorizationDialog(message="falta existencia", presenter=presentador)
        dlg._reason.setText("urge")
        dlg._authorize()
        assert dlg.authorizer_user_id is None

    def test_usuario_y_clave_validos_con_motivo_autorizan(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ProductionAuthorizationDialog,
        )

        dlg = ProductionAuthorizationDialog(message="falta existencia",
                                            presenter=_Presentador([]))
        dlg._reason.setText("Pollo ya en la mesa")
        dlg._authorize()
        assert dlg.authorizer_user_id == "gerente-id"
        assert dlg.reason == "Pollo ya en la mesa"


class TestReintentoConAutorizacion:
    def _pagina(self, app, presentador, monkeypatch):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecuteProcessingOrderDialog,
            ExecutionResultDialog,
            ProductionAuthorizationDialog,
        )
        from frontend.desktop.modules.meat_processing.pages import processing_orders_page as pag

        monkeypatch.setattr(ExecuteProcessingOrderDialog, "exec_",
                            lambda self: QtWidgets.QDialog.Accepted)
        monkeypatch.setattr(ExecutionResultDialog, "exec_",
                            lambda self: QtWidgets.QDialog.Accepted)

        def _autoriza(self):
            self.authorizer_user_id, self.reason = "gerente-id", "Pollo ya en la mesa"
            return QtWidgets.QDialog.Accepted

        monkeypatch.setattr(ProductionAuthorizationDialog, "exec_", _autoriza)
        monkeypatch.setattr(pag.QMessageBox, "warning", lambda *a, **k: None)
        monkeypatch.setattr(pag.QMessageBox, "information", lambda *a, **k: None)
        pagina = pag.ProcessingOrdersPage(presentador)
        monkeypatch.setattr(pagina, "_selected_order_id", lambda: "o1")
        return pagina

    def test_sin_existencia_reintenta_con_el_autorizador(self, app, monkeypatch):
        presentador = _Presentador([
            (False, "falta existencia", {"error_code": "STOCK_AUTHORIZATION_REQUIRED"}),
            (True, "Orden ejecutada y cerrada", {"results": []}),
        ])
        self._pagina(app, presentador, monkeypatch)._on_execute()
        assert len(presentador.llamadas) == 2
        segundo = presentador.llamadas[1]
        assert segundo["stock_authorizer_user_id"] == "gerente-id"
        assert segundo["stock_reason"] == "Pollo ya en la mesa"

    def test_fuera_de_tolerancia_manda_al_autorizador_de_rendimiento(self, app, monkeypatch):
        presentador = _Presentador([
            (False, "fuera de tolerancia", {"error_code": "YIELD_AUTHORIZATION_REQUIRED"}),
            (True, "Orden ejecutada y cerrada", {"results": []}),
        ])
        self._pagina(app, presentador, monkeypatch)._on_execute()
        assert presentador.llamadas[1]["variance_authorizer_user_id"] == "gerente-id"
        assert "stock_authorizer_user_id" not in presentador.llamadas[1]

    def test_otro_error_no_pide_autorizacion(self, app, monkeypatch):
        presentador = _Presentador([
            (False, "la entrada no tiene costo", {"error_code": "MISSING_INPUT_COST"})])
        self._pagina(app, presentador, monkeypatch)._on_execute()
        assert len(presentador.llamadas) == 1

    def test_una_orden_sin_despiece_no_abre_la_captura(self, app, monkeypatch):
        presentador = _Presentador([])
        presentador.execution_plan = lambda oid: {**PLAN, "has_despiece": False}
        self._pagina(app, presentador, monkeypatch)._on_execute()
        assert presentador.llamadas == []


class TestCasillasDeUsoDeAlmacenes:
    def test_el_alta_ofrece_los_cuatro_usos(self, app):
        from frontend.desktop.modules.inventory.dialogs import CreateWarehouseDialog

        dlg = CreateWarehouseDialog()
        assert set(dlg.purposes()) == {"allow_sales_allocation", "allow_purchase_receipt",
                                       "allow_production", "allow_quarantine"}
        # mismos valores iniciales que el dominio
        assert dlg.purposes() == {"allow_sales_allocation": True,
                                  "allow_purchase_receipt": True,
                                  "allow_production": False, "allow_quarantine": False}

    def test_marcar_produccion_se_refleja_en_lo_capturado(self, app):
        from frontend.desktop.modules.inventory.dialogs import CreateWarehouseDialog

        dlg = CreateWarehouseDialog()
        dlg.purpose_checks["allow_production"].setChecked(True)
        assert dlg.purposes()["allow_production"] is True

    def test_la_edicion_prellena_lo_que_el_almacen_ya_tiene(self, app):
        from frontend.desktop.modules.inventory.dialogs import EditWarehouseDialog

        dlg = EditWarehouseDialog(warehouse={
            "code": "PLANTA", "name": "Planta", "warehouse_type": "STORE",
            "allow_sales_allocation": 0, "allow_purchase_receipt": 1,
            "allow_production": 1, "allow_quarantine": 0})
        assert dlg.purposes() == {"allow_sales_allocation": False,
                                  "allow_purchase_receipt": True,
                                  "allow_production": True, "allow_quarantine": False}

    def test_el_presenter_solo_reenvia_los_usos_que_el_dominio_conoce(self):
        from frontend.desktop.modules.inventory.presenter import _purposes

        assert _purposes({"allow_production": 1, "inventado": True}) == {
            "allow_production": True}
        assert _purposes(None) == {}

    def test_la_lista_dice_para_que_sirve_cada_almacen(self):
        from frontend.desktop.modules.inventory.view_models import warehouses_table

        vm = warehouses_table([
            {"id": "w1", "code": "PLANTA", "name": "Planta", "warehouse_type": "STORE",
             "status": "ACTIVE", "allow_production": 1},
            {"id": "w2", "code": "X", "name": "Sin uso", "warehouse_type": "STORE",
             "status": "ACTIVE"}])
        assert vm.rows[0][4] == "Producción"
        assert vm.rows[1][4] == "—"
