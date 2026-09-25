"""La pantalla que ejecuta una orden preparada.

- La captura propone lo RESERVADO por insumo y lo ESPERADO por salida (de la
  definición congelada) y no deja ejecutar sin pesos.
- Si una salida queda fuera de tolerancia, se pide la autorización de otro
  usuario (usuario, clave, motivo) y se REINTENTA: el caso de uso es
  reanudable. Ya no existe "producir sin existencia": no hay consumo sin reserva.
- Una orden sin definición congelada o sin reserva no abre la captura.
- El resultado no muestra UUIDs ni costos (los asigna Costos).
- Las casillas de uso de Almacenes llegan hasta el presenter.
"""
from __future__ import annotations

import os
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)

INSUMO = "01a0d1b0-0000-7000-8000-000000000001"
SALIDA = "01a0d1b0-0000-7000-8000-000000000002"
MERMA = "01a0d1b0-0000-7000-8000-000000000003"


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


PLAN = {"order_id": "o1", "status": "RELEASED", "has_definition": True,
        "effective_version": "esquema v2",
        "inputs": [{"product_id": INSUMO, "product_name": "Filete de pescado entero",
                    "reserved_weight": Decimal("10"), "lot_controlled": True,
                    "lots": [{"lot_id": "l1", "quantity": Decimal("10")}]}],
        "outputs": [{"product_id": SALIDA, "product_name": "Filete limpio",
                     "output_type": "MAIN_PRODUCT", "expected_weight": Decimal("6.5"),
                     "quality_gate": True, "goes_to_stock": True},
                    {"product_id": MERMA, "product_name": "Espinas",
                     "output_type": "WASTE", "expected_weight": Decimal("3.5"),
                     "quality_gate": False, "goes_to_stock": False}],
        "reserved_total": Decimal("10")}


class _Presentador:
    """Presenter de mentira: registra lo que la pantalla le pide."""

    def __init__(self, respuestas, *, autorizador=("gerente-id", ""), plan=PLAN):
        self.respuestas = list(respuestas)
        self.autorizador = autorizador
        self.plan = plan
        self.llamadas = []

    def execution_plan(self, order_id):
        return self.plan

    def execute_order(self, **kwargs):
        self.llamadas.append(kwargs)
        return self.respuestas.pop(0)

    def verify_authorizer(self, usuario, clave):
        return self.autorizador

    def orders(self):
        return SimpleNamespace(rows=[], row_ids=[])


def _textos(tabla):
    modelo = tabla.model()
    return [str(modelo.index(r, c).data() or "") for r in range(modelo.rowCount())
            for c in range(modelo.columnCount())]


class TestCapturaDeEjecucion:
    def test_propone_lo_reservado_y_lo_esperado(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecuteProcessingOrderDialog,
        )

        dlg = ExecuteProcessingOrderDialog(plan=PLAN)
        assert dlg.inputs() == [{"product_id": INSUMO, "weight": Decimal("10")}]
        pesos = {o["product_id"]: o["weight"] for o in dlg.outputs()}
        assert pesos == {SALIDA: Decimal("6.5"), MERMA: Decimal("3.5")}

    def test_no_ejecuta_sin_peso_consumido(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecuteProcessingOrderDialog,
        )

        dlg = ExecuteProcessingOrderDialog(plan=PLAN)
        for campo in dlg._entradas.values():
            campo.set_decimal(Decimal("0"))
        dlg._accept_if_valid()
        assert dlg.result() != QtWidgets.QDialog.Accepted

    def test_no_ejecuta_sin_peso_de_ninguna_salida(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecuteProcessingOrderDialog,
        )

        dlg = ExecuteProcessingOrderDialog(plan=PLAN)
        for campo in dlg._campos.values():
            campo.set_decimal(Decimal("0"))
        dlg._accept_if_valid()
        assert dlg.result() != QtWidgets.QDialog.Accepted

    def test_ninguna_tabla_muestra_uuids(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecuteProcessingOrderDialog,
            ExecutionResultDialog,
        )

        captura = ExecuteProcessingOrderDialog(plan=PLAN)
        resultado = ExecutionResultDialog(
            message="Orden ejecutada y cerrada", names={SALIDA: "Filete limpio"},
            results=[{"product_id": SALIDA, "expected_weight": "6.5", "actual_weight": "6.4",
                      "difference_weight": "-0.1", "yield_pct": "64", "variance_pct": "-1.54",
                      "output_lot_id": "01a0d1b0-0000-7000-8000-00000000000f"}])
        for tabla in (captura.inputs_table, captura.table, resultado.table):
            textos = _textos(tabla)
            assert textos and not any("01a0d1b0-" in x for x in textos), textos

    def test_el_resultado_no_muestra_costos(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecutionResultDialog,
        )

        dlg = ExecutionResultDialog(message="ok", results=[])
        modelo = dlg.table.model()
        encabezados = [str(modelo.headerData(c, 1)) for c in range(modelo.columnCount())]
        assert encabezados and not any("osto" in h for h in encabezados)


class TestAutorizacionDeRendimiento:
    def test_exige_motivo(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ProductionAuthorizationDialog,
        )

        dlg = ProductionAuthorizationDialog(message="fuera de tolerancia",
                                            presenter=_Presentador([]))
        dlg._authorize()
        assert dlg.authorizer_user_id is None

    def test_clave_incorrecta_no_autoriza(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ProductionAuthorizationDialog,
        )

        presentador = _Presentador([], autorizador=(None, "Usuario o clave incorrectos"))
        dlg = ProductionAuthorizationDialog(message="fuera de tolerancia",
                                            presenter=presentador)
        dlg._reason.setText("urge")
        dlg._authorize()
        assert dlg.authorizer_user_id is None

    def test_usuario_y_clave_validos_con_motivo_autorizan(self, app):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ProductionAuthorizationDialog,
        )

        dlg = ProductionAuthorizationDialog(message="fuera de tolerancia",
                                            presenter=_Presentador([]))
        dlg._reason.setText("Pieza con espinas de más")
        dlg._authorize()
        assert dlg.authorizer_user_id == "gerente-id"
        assert dlg.reason == "Pieza con espinas de más"


class TestReintentoConAutorizacion:
    def _pagina(self, app, presentador, monkeypatch):
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecuteProcessingOrderDialog,
            ExecutionResultDialog,
            ProductionAuthorizationDialog,
        )
        from frontend.desktop.modules.meat_processing.pages import processing_orders_page as pag

        self.avisos = []
        monkeypatch.setattr(ExecuteProcessingOrderDialog, "exec_",
                            lambda self: QtWidgets.QDialog.Accepted)
        monkeypatch.setattr(ExecutionResultDialog, "exec_",
                            lambda self: QtWidgets.QDialog.Accepted)

        def _autoriza(self):
            self.authorizer_user_id, self.reason = "gerente-id", "Pieza con espinas de más"
            return QtWidgets.QDialog.Accepted

        monkeypatch.setattr(ProductionAuthorizationDialog, "exec_", _autoriza)
        monkeypatch.setattr(pag.QMessageBox, "warning",
                            lambda *a, **k: self.avisos.append(a[2]))
        monkeypatch.setattr(pag.QMessageBox, "information", lambda *a, **k: None)
        pagina = pag.ProcessingOrdersPage(presentador)
        monkeypatch.setattr(pagina, "_selected_order_id", lambda: "o1")
        return pagina

    def test_fuera_de_tolerancia_reintenta_con_el_autorizador(self, app, monkeypatch):
        presentador = _Presentador([
            (False, "fuera de tolerancia", {"error_code": "YIELD_AUTHORIZATION_REQUIRED"}),
            (True, "Orden ejecutada y cerrada", {"results": []}),
        ])
        self._pagina(app, presentador, monkeypatch)._on_execute()
        assert len(presentador.llamadas) == 2
        segundo = presentador.llamadas[1]
        assert segundo["variance_authorizer_user_id"] == "gerente-id"
        assert segundo["variance_reason"] == "Pieza con espinas de más"
        assert segundo["inputs"] == [{"product_id": INSUMO, "weight": Decimal("10")}]
        assert "stock_authorizer_user_id" not in segundo

    def test_otro_error_no_pide_autorizacion(self, app, monkeypatch):
        presentador = _Presentador([
            (False, "Costos no podrá costear la orden", {"error_code": "MISSING_INPUT_COST"})])
        self._pagina(app, presentador, monkeypatch)._on_execute()
        assert len(presentador.llamadas) == 1

    def test_una_orden_sin_definicion_congelada_no_abre_la_captura(self, app, monkeypatch):
        presentador = _Presentador([], plan={**PLAN, "has_definition": False})
        self._pagina(app, presentador, monkeypatch)._on_execute()
        assert presentador.llamadas == []
        assert "prepárala" in self.avisos[0]

    def test_una_orden_sin_reserva_no_abre_la_captura(self, app, monkeypatch):
        sin_reserva = {**PLAN, "inputs": [{**PLAN["inputs"][0],
                                           "reserved_weight": Decimal("0"), "lots": []}]}
        presentador = _Presentador([], plan=sin_reserva)
        self._pagina(app, presentador, monkeypatch)._on_execute()
        assert presentador.llamadas == []
        assert "reservados" in self.avisos[0]


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
