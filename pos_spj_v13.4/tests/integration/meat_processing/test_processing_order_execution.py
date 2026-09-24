"""Ejecutar una orden de despiece de punta a punta (Fase 10, §10/§13/§14).

Antes de esto la pantalla conectaba 4 de ~50 casos de uso y NINGUNA orden podía
cerrarse: los puertos a Inventario, Costos y Mermas eran nulos. Lo que se fija
aquí es la cadena completa contra los casos de uso reales —consumo, salidas,
calidad, recepción con lote, resultado por corte, conciliación y cierre— y las
dos puertas de autorización en caliente que decidió el usuario.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.meat_processing.authorization import (
    MeatProcessingAuthorizationPolicy,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.use_cases.order_execution_use_cases import (
    ExecuteProcessingOrderUseCase,
    ProcessingOrderExecutionQueryService,
)
from backend.domain.meat_processing.enums import ProcessingOrderStatus
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._execution_fixture import Planta, build_db

#: Regla cero: toda identidad es UUIDv7, también la de quien opera.
OPERARIO, GERENTE = new_uuid(), new_uuid()


class _Checker:
    """Permisos del AUTORIZADOR (otro usuario), no los de la sesión."""

    def __init__(self, permisos_por_usuario: dict) -> None:
        self._permisos = permisos_por_usuario

    def has_permission(self, user_id, permission) -> bool:
        return str(permission) in self._permisos.get(str(user_id), ())


@pytest.fixture()
def planta():
    conn = build_db()
    try:
        yield Planta(conn)
    finally:
        conn.close()


def _uc(permisos_autorizador=None):
    auth = MeatProcessingAuthorizationPolicy.permissive_for_tests()
    return ExecuteProcessingOrderUseCase(
        auth, authorizer_checker=_Checker(permisos_autorizador or {}))


def _ejecutar(planta, order_id, *, pesos=None, uc=None, actor=OPERARIO, **kwargs):
    pesos = pesos or {"pechuga": "3.4", "pierna": "3.0", "ala": "1.2", "merma": "0.5"}
    ids = {"pechuga": planta.pechuga, "pierna": planta.pierna, "ala": planta.ala,
           "merma": planta.merma}
    return (uc or _uc()).execute(
        planta.conn, order_id=order_id, input_weight=kwargs.pop("input_weight", "10"),
        outputs=[{"product_id": ids[n], "weight": w} for n, w in pesos.items()],
        actor_user_id=actor, operation_id=new_uuid(), **kwargs)


class TestPlanDeCaptura:
    def test_lo_esperado_sale_del_despiece_capturado_al_liberar(self, planta):
        plan = ProcessingOrderExecutionQueryService(planta.conn).plan(planta.orden_liberada())
        assert plan["has_despiece"] is True
        assert plan["planned_weight"] == Decimal("10")
        esperados = {s.product_id: s.expected_weight for s in plan["outputs"]}
        assert esperados[planta.pechuga] == Decimal("3.500")   # 0.35 × 10 kg
        assert esperados[planta.merma] == Decimal("0.500")

    def test_orden_inexistente_no_revienta(self, planta):
        assert ProcessingOrderExecutionQueryService(planta.conn).plan(new_uuid()) is None


class TestEjecucionCompleta:
    def test_la_orden_se_cierra_y_mueve_existencia_real(self, planta):
        oid = planta.orden_liberada()
        r = _ejecutar(planta, oid)
        assert r.success, r.message
        assert planta.conn.execute(
            "SELECT status FROM processing_orders WHERE id=?", (oid,)
        ).fetchone()[0] == ProcessingOrderStatus.CLOSED.value
        assert planta.saldo(planta.pollo) == Decimal("0.000")      # 10 consumidos
        assert planta.saldo(planta.pechuga) == Decimal("3.400")
        assert planta.saldo(planta.pierna) == Decimal("3.000")
        assert planta.saldo(planta.ala) == Decimal("1.200")

    def test_la_merma_no_entra_a_existencia(self, planta):
        _ejecutar(planta, planta.orden_liberada())
        assert planta.saldo(planta.merma) == Decimal("0.000")

    def test_el_costo_de_la_entrada_se_reparte_completo_entre_los_cortes(self, planta):
        r = _ejecutar(planta, planta.orden_liberada())
        repartido = sum(Decimal(str(f["allocated_cost"])) for f in r.data["results"])
        assert repartido == Decimal("500.00")                      # 10 kg × 50
        por_id = {f["product_id"]: f for f in r.data["results"]}
        assert Decimal(str(por_id[planta.pechuga]["allocated_cost"])) == Decimal("283.33")
        assert Decimal(str(por_id[planta.merma]["allocated_cost"])) == Decimal("0")

    def test_cada_corte_deja_su_resultado_con_esperado_real_y_variacion(self, planta):
        r = _ejecutar(planta, planta.orden_liberada())
        pechuga = [f for f in r.data["results"] if f["product_id"] == planta.pechuga][0]
        assert Decimal(str(pechuga["expected_weight"])) == Decimal("3.500")
        assert Decimal(str(pechuga["actual_weight"])) == Decimal("3.400")
        assert Decimal(str(pechuga["difference_weight"])) == Decimal("-0.100")
        assert Decimal(str(pechuga["variance_pct"])) == Decimal("-2.86")
        assert pechuga["output_lot_id"]        # recibido con lote, trazable

    def test_las_salidas_recibidas_tienen_lote(self, planta):
        _ejecutar(planta, planta.orden_liberada())
        lotes = planta.conn.execute("SELECT COUNT(*) FROM inventory_lots").fetchone()[0]
        assert lotes == 3                      # los tres cortes buenos, no la merma

    def test_el_costo_promedio_queda_proyectado_por_corte(self, planta):
        _ejecutar(planta, planta.orden_liberada())
        costos = dict(planta.conn.execute(
            "SELECT product_id, CAST(average_cost AS REAL) FROM product_cost").fetchall())
        assert round(costos[planta.pechuga], 2) == 83.33


class TestSinExistenciaDeLaEntrada:
    def test_sin_autorizacion_no_se_produce(self, planta):
        conn = planta.conn
        conn.execute("UPDATE inventory_balances SET quantity='1' WHERE product_id=?",
                     (planta.pollo,))
        conn.commit()
        r = _ejecutar(planta, planta.orden_liberada())
        assert not r.success and r.error_code == "STOCK_AUTHORIZATION_REQUIRED"
        assert planta.saldo(planta.pechuga) == Decimal("0.000")   # nada se movió

    def test_autorizada_por_otro_usuario_con_permiso_si_produce(self, planta):
        conn = planta.conn
        conn.execute("UPDATE inventory_balances SET quantity='1' WHERE product_id=?",
                     (planta.pollo,))
        conn.commit()
        uc = _uc({GERENTE: (MeatProcessingPermissions.CONSUMPTION_OVERRIDE,)})
        r = _ejecutar(planta, planta.orden_liberada(), uc=uc,
                      stock_authorizer_user_id=GERENTE, stock_reason="Pollo ya en la mesa")
        assert r.success, r.message
        assert r.data["stock_authorized"] is True
        assert planta.saldo(planta.pollo) == Decimal("-9.000")    # negativo autorizado

    def test_quien_ejecuta_no_puede_autorizarse_a_si_mismo(self, planta):
        conn = planta.conn
        conn.execute("UPDATE inventory_balances SET quantity='1' WHERE product_id=?",
                     (planta.pollo,))
        conn.commit()
        uc = _uc({OPERARIO: (MeatProcessingPermissions.CONSUMPTION_OVERRIDE,)})
        r = _ejecutar(planta, planta.orden_liberada(), uc=uc,
                      stock_authorizer_user_id=OPERARIO, stock_reason="me autorizo")
        assert not r.success and r.error_code == "SEGREGATION_OF_DUTIES"

    def test_autorizador_sin_el_permiso_no_alcanza(self, planta):
        conn = planta.conn
        conn.execute("UPDATE inventory_balances SET quantity='1' WHERE product_id=?",
                     (planta.pollo,))
        conn.commit()
        r = _ejecutar(planta, planta.orden_liberada(), uc=_uc({GERENTE: ()}),
                      stock_authorizer_user_id=GERENTE, stock_reason="dale")
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_la_autorizacion_exige_motivo(self, planta):
        conn = planta.conn
        conn.execute("UPDATE inventory_balances SET quantity='1' WHERE product_id=?",
                     (planta.pollo,))
        conn.commit()
        uc = _uc({GERENTE: (MeatProcessingPermissions.CONSUMPTION_OVERRIDE,)})
        r = _ejecutar(planta, planta.orden_liberada(), uc=uc,
                      stock_authorizer_user_id=GERENTE, stock_reason="   ")
        assert not r.success and r.error_code == "STOCK_AUTHORIZATION_REQUIRED"


class TestRendimientoFueraDeTolerancia:
    #: la mitad de la pechuga esperada: −50%, muy por debajo del 5% tolerado
    POBRE = {"pechuga": "1.7", "pierna": "3.0", "ala": "1.2", "merma": "0.5"}

    def test_sin_autorizacion_no_se_cierra(self, planta):
        r = _ejecutar(planta, planta.orden_liberada(), pesos=self.POBRE)
        assert not r.success and r.error_code == "YIELD_AUTHORIZATION_REQUIRED"
        assert planta.saldo(planta.pechuga) == Decimal("0.000")

    def test_autorizada_cierra_y_abre_caso_en_mermas(self, planta):
        uc = _uc({GERENTE: (MeatProcessingPermissions.YIELD_OVERRIDE,)})
        r = _ejecutar(planta, planta.orden_liberada(), pesos=self.POBRE, uc=uc,
                      variance_authorizer_user_id=GERENTE,
                      variance_reason="Pollo de baja calidad")
        assert r.success, r.message
        assert r.data["out_of_tolerance"] is True
        caso = planta.conn.execute(
            "SELECT origin, source_module, requires_inventory_posting FROM loss_cases"
        ).fetchall()
        assert len(caso) == 1
        assert caso[0][0] == "PRODUCTION" and caso[0][1] == "production"
        # La merma ya quedó reflejada al no recibirla en existencia: el caso
        # documenta la diferencia, no vuelve a descontar.
        assert not caso[0][2]

    def test_dentro_de_tolerancia_no_pide_nada(self, planta):
        r = _ejecutar(planta, planta.orden_liberada())
        assert r.success and r.data["out_of_tolerance"] is False


class TestValidacionAntesDeMutar:
    def test_sin_costo_de_entrada_no_se_inventa_uno(self, planta):
        planta.conn.execute("DELETE FROM product_cost")
        planta.conn.commit()
        r = _ejecutar(planta, planta.orden_liberada())
        assert not r.success and r.error_code == "MISSING_INPUT_COST"
        assert planta.saldo(planta.pollo) == Decimal("10.000")   # intacto

    def test_corte_sin_precio_de_venta_falla_sin_consumir_la_entrada(self, planta):
        planta.conn.execute("DELETE FROM product_price WHERE product_id=?", (planta.pechuga,))
        planta.conn.commit()
        r = _ejecutar(planta, planta.orden_liberada())
        assert not r.success and r.error_code == "COST_ALLOCATION_FAILED"
        assert planta.saldo(planta.pollo) == Decimal("10.000")

    def test_un_producto_ajeno_al_despiece_se_rechaza(self, planta):
        r = (_uc()).execute(
            planta.conn, order_id=planta.orden_liberada(), input_weight="10",
            outputs=[{"product_id": new_uuid(), "weight": "3"}],
            actor_user_id=OPERARIO, operation_id=new_uuid())
        assert not r.success and r.error_code == "INVALID_OUTPUT"

    def test_sin_peso_de_entrada_no_se_ejecuta(self, planta):
        r = _ejecutar(planta, planta.orden_liberada(), input_weight="0")
        assert not r.success and r.error_code == "INVALID_INPUT"

    def test_sin_salida_productiva_no_se_ejecuta(self, planta):
        r = _ejecutar(planta, planta.orden_liberada(),
                      pesos={"pechuga": "0", "pierna": "0", "ala": "0", "merma": "10"})
        assert not r.success and r.error_code == "INVALID_OUTPUT"

    def test_una_orden_no_liberada_no_se_ejecuta(self, planta):
        oid = planta.orden_liberada()
        assert _ejecutar(planta, oid).success
        r = _ejecutar(planta, oid)               # ya cerrada
        assert not r.success and r.error_code == "INVALID_STATE"

    def test_orden_inexistente(self, planta):
        r = _ejecutar(planta, new_uuid())
        assert not r.success and r.error_code == "ORDER_NOT_FOUND"


class TestReanudable:
    def test_reintentar_tras_un_fallo_continua_sin_duplicar(self, planta):
        """El fallo del primer intento ya había consumido la entrada; el
        segundo no la vuelve a descontar."""
        oid = planta.orden_liberada()
        original = _uc()

        class _Rompe(ExecuteProcessingOrderUseCase):
            def _run(self, connection, p, **kw):
                from backend.application.meat_processing.use_cases import output_use_cases

                real = output_use_cases.RecordProcessOutputsUseCase

                class _Falla(real):
                    def execute(self, *a, **k):
                        from backend.application.meat_processing.result import (
                            MeatProcessingResult,
                        )
                        return MeatProcessingResult.fail("falla simulada", "BOOM")

                output_use_cases.RecordProcessOutputsUseCase = _Falla
                try:
                    return super()._run(connection, p, **kw)
                finally:
                    output_use_cases.RecordProcessOutputsUseCase = real

        roto = _Rompe(MeatProcessingAuthorizationPolicy.permissive_for_tests())
        primero = _ejecutar(planta, oid, uc=roto)
        assert not primero.success
        assert planta.saldo(planta.pollo) == Decimal("0.000")     # ya consumida

        segundo = _ejecutar(planta, oid)
        assert segundo.success, segundo.message
        assert planta.saldo(planta.pollo) == Decimal("0.000")     # NO se duplicó
        assert planta.saldo(planta.pechuga) == Decimal("3.400")


class TestRegistroPorCorte:
    """§13: el resultado por corte es un registro consultable, no sólo el
    diálogo del momento. La conciliación que ya existía es por ORDEN."""

    def test_lo_ejecutado_queda_en_el_registro_de_la_sucursal(self, planta):
        from backend.application.meat_processing.queries.meat_processing_records_query_service import (  # noqa: E501
            MeatProcessingRecord,
            MeatProcessingRecordsQueryService,
        )

        _ejecutar(planta, planta.orden_liberada())
        pagina = MeatProcessingRecordsQueryService(planta.conn).list_records(
            planta.branch, MeatProcessingRecord.OUTPUT_RESULTS)
        assert pagina.total == 4                      # los 3 cortes y la merma
        assert {f["output_type"] for f in pagina.rows} == {
            "MAIN_PRODUCT", "CO_PRODUCT", "WASTE"}
        merma = [f for f in pagina.rows if f["output_type"] == "WASTE"][0]
        assert Decimal(merma["allocated_cost"]) == Decimal("0")
        assert merma["output_lot_id"] is None          # la merma no se recibe
        buenos = [f for f in pagina.rows if f["output_type"] != "WASTE"]
        assert all(f["output_lot_id"] and Decimal(f["allocated_cost"]) > 0 for f in buenos)

    def test_el_registro_no_cruza_sucursales(self, planta):
        from backend.application.meat_processing.queries.meat_processing_records_query_service import (  # noqa: E501
            MeatProcessingRecord,
            MeatProcessingRecordsQueryService,
        )

        _ejecutar(planta, planta.orden_liberada())
        pagina = MeatProcessingRecordsQueryService(planta.conn).list_records(
            new_uuid(), MeatProcessingRecord.OUTPUT_RESULTS)
        assert pagina.total == 0
