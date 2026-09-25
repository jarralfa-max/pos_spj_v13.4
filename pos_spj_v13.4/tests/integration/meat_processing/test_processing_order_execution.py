"""Ejecutar una orden preparada de punta a punta (Fase 10 → auditoría profunda).

La ejecución consume EXACTAMENTE lo que Inventario reservó al preparar, recibe
las salidas con lote en la ubicación que resuelve Inventario, pide el costeo a
Costos (no lo calcula) y es reanudable. Aquí el producto es un lomo de cerdo;
nada del código sabe qué es: el comportamiento sale del esquema de corte.

Reglas que ya NO existen y por qué:
- "producir sin existencia autorizado por otro usuario" (saldo negativo): no
  hay consumo sin reserva real, y no hay reserva sin existencia.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.meat_processing.authorization import (
    MeatProcessingAuthorizationPolicy,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.queries.processing_order_execution_query_service import (
    ProcessingOrderExecutionQueryService,
)
from backend.application.meat_processing.use_cases.order_execution_use_cases import (
    ExecuteProcessingOrderUseCase,
)
from backend.domain.meat_processing.enums import ProcessingOrderStatus, ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.infrastructure.integrations.meat_processing_execution_ports import (
    execution_ports_factory,
)
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._generic_plant import Planta, build_db


class _Checker:
    """Permisos del AUTORIZADOR (otro usuario), no los de la sesión."""

    def __init__(self, permisos_por_usuario: dict) -> None:
        self._permisos = permisos_por_usuario

    def has_permission(self, user_id, permission) -> bool:
        return str(permission) in self._permisos.get(str(user_id), ())


class _Lomo:
    """Lomo de cerdo entero → chuleta, recorte y grasa (merma)."""

    def __init__(self) -> None:
        self.conn = build_db()
        p = self.p = Planta(self.conn)
        porcino = p.especie("Porcino")
        self.lomo = p.producto("Lomo de cerdo entero", lote=True, especie=porcino)
        self.chuleta = p.producto("Chuleta", lote=True, especie=porcino)
        self.recorte = p.producto("Recorte", lote=True, especie=porcino)
        self.grasa = p.producto("Grasa", especie=porcino)
        p.despiece(self.lomo, [(self.chuleta, "MAIN_PRODUCT", "0.60"),
                               (self.recorte, "CO_PRODUCT", "0.30"),
                               (self.grasa, "WASTE", "0.10")], especie=porcino)
        p.costo(self.lomo, "80")
        p.precio(self.chuleta, "150"); p.precio(self.recorte, "90"); p.precio(self.grasa, "2")
        self.lote = p.existencia(self.lomo, "20", lote="LOMO-7", vence="2031-01-01")

    def orden(self, peso="10"):
        return self.p.lista(ProcessType.DISASSEMBLY, self.lomo, peso)

    def salidas(self, chuleta="6", recorte="3", grasa="1"):
        return {self.chuleta: chuleta, self.recorte: recorte, self.grasa: grasa}


@pytest.fixture()
def lomo():
    planta = _Lomo()
    try:
        yield planta
    finally:
        planta.conn.close()


def _uc(permisos_autorizador=None, ports_factory=None):
    return ExecuteProcessingOrderUseCase(
        MeatProcessingAuthorizationPolicy.permissive_for_tests(),
        ports_factory=ports_factory or execution_ports_factory(),
        authorizer_checker=_Checker(permisos_autorizador or {}))


def _ejecutar(lomo, oid, *, salidas=None, uc=None, entradas=None, **kwargs):
    return (uc or _uc()).execute(
        lomo.conn, order_id=oid, actor_user_id=lomo.p.operario, operation_id=new_uuid(),
        outputs=[{"product_id": p, "weight": Decimal(k)}
                 for p, k in (salidas or lomo.salidas()).items()],
        inputs=(None if entradas is None else
                [{"product_id": p, "weight": Decimal(k)} for p, k in entradas.items()]),
        **kwargs)


def _estado(lomo, oid):
    return MeatProcessingUnitOfWork(lomo.conn).orders.get(oid).status


class TestPlanDeCaptura:
    def test_lo_esperado_y_lo_reservado_salen_de_la_definicion_congelada(self, lomo):
        plan = ProcessingOrderExecutionQueryService(lomo.conn).plan(lomo.orden())
        assert plan["has_definition"] is True
        entrada = plan["inputs"][0]
        assert (entrada["product_id"], entrada["reserved_weight"]) == (lomo.lomo, Decimal("10"))
        assert [l["lot_id"] for l in entrada["lots"]] == [lomo.lote]
        esperados = {s["product_id"]: s["expected_weight"] for s in plan["outputs"]}
        assert esperados[lomo.chuleta] == Decimal("6.000")
        assert esperados[lomo.grasa] == Decimal("1.000")

    def test_orden_inexistente_no_revienta(self, lomo):
        assert ProcessingOrderExecutionQueryService(lomo.conn).plan(new_uuid()) is None


class TestEjecucionCompleta:
    def test_la_orden_se_cierra_y_mueve_existencia_real(self, lomo):
        oid = lomo.orden()
        r = _ejecutar(lomo, oid)
        assert r.success, r.message
        assert _estado(lomo, oid) is ProcessingOrderStatus.CLOSED
        assert lomo.p.saldo(lomo.lomo) == Decimal("10")         # 20 − 10 consumidos
        assert lomo.p.reservado(lomo.lomo) == Decimal("0")      # la reserva se cumplió
        assert lomo.p.saldo(lomo.chuleta) == Decimal("6")
        assert lomo.p.saldo(lomo.recorte) == Decimal("3")

    def test_la_merma_no_entra_a_existencia(self, lomo):
        _ejecutar(lomo, lomo.orden())
        assert lomo.p.saldo(lomo.grasa) == Decimal("0")

    def test_consumir_menos_de_lo_reservado_suelta_el_resto(self, lomo):
        oid = lomo.orden()
        r = _ejecutar(lomo, oid, entradas={lomo.lomo: "8"},
                      salidas=lomo.salidas("4.8", "2.4", "0.8"))
        assert r.success, r.message
        assert lomo.p.saldo(lomo.lomo) == Decimal("12")
        assert lomo.p.reservado(lomo.lomo) == Decimal("0")

    def test_no_se_consume_mas_de_lo_reservado(self, lomo):
        oid = lomo.orden()
        r = _ejecutar(lomo, oid, entradas={lomo.lomo: "12"},
                      salidas=lomo.salidas("7.2", "3.6", "1.2"))
        assert not r.success and r.error_code == "EXCEEDS_RESERVATION"
        assert lomo.p.saldo(lomo.lomo) == Decimal("20")          # nada se movió

    def test_cada_salida_deja_su_resultado_con_esperado_real_y_variacion(self, lomo):
        r = _ejecutar(lomo, lomo.orden(), salidas=lomo.salidas("5.9", "3.1", "1"))
        chuleta = [f for f in r.data["results"] if f["product_id"] == lomo.chuleta][0]
        assert Decimal(str(chuleta["expected_weight"])) == Decimal("6.000")
        assert Decimal(str(chuleta["actual_weight"])) == Decimal("5.900")
        assert Decimal(str(chuleta["difference_weight"])) == Decimal("-0.100")
        assert Decimal(str(chuleta["variance_pct"])) == Decimal("-1.67")
        assert chuleta["input_lot_id"] == lomo.lote
        assert chuleta["output_lot_id"]

    def test_las_salidas_recibidas_tienen_lote_y_la_merma_no(self, lomo):
        r = _ejecutar(lomo, lomo.orden())
        lotes = {f["product_id"]: f["output_lot_id"] for f in r.data["results"]}
        assert lotes[lomo.chuleta] and lotes[lomo.recorte]
        assert lotes[lomo.grasa] is None


class TestRendimientoFueraDeTolerancia:
    #: la mitad de la chuleta esperada: −50 %, muy por debajo de lo tolerado
    POBRE = ("3", "3", "4")

    def test_sin_autorizacion_no_se_ejecuta_nada(self, lomo):
        r = _ejecutar(lomo, lomo.orden(), salidas=lomo.salidas(*self.POBRE))
        assert not r.success and r.error_code == "YIELD_AUTHORIZATION_REQUIRED"
        assert lomo.p.saldo(lomo.chuleta) == Decimal("0")
        assert lomo.p.saldo(lomo.lomo) == Decimal("20")          # en existencia, sin consumir
        assert lomo.p.reservado(lomo.lomo) == Decimal("10")      # y la reserva sigue viva

    def test_autorizada_cierra_y_abre_caso_en_mermas(self, lomo):
        uc = _uc({lomo.p.gerente: (MeatProcessingPermissions.YIELD_OVERRIDE,)})
        r = _ejecutar(lomo, lomo.orden(), salidas=lomo.salidas(*self.POBRE), uc=uc,
                      variance_authorizer_user_id=lomo.p.gerente,
                      variance_reason="Pieza con exceso de grasa")
        assert r.success, r.message
        assert r.data["out_of_tolerance"] is True
        casos = lomo.conn.execute(
            "SELECT origin, requires_inventory_posting FROM loss_cases").fetchall()
        assert len(casos) == 1
        # La diferencia ya quedó reflejada al consumir y producir: el caso la
        # documenta y la valúa; no vuelve a descontar existencia.
        assert not casos[0][1]

    def test_quien_ejecuta_no_puede_autorizarse_a_si_mismo(self, lomo):
        uc = _uc({lomo.p.operario: (MeatProcessingPermissions.YIELD_OVERRIDE,)})
        r = _ejecutar(lomo, lomo.orden(), salidas=lomo.salidas(*self.POBRE), uc=uc,
                      variance_authorizer_user_id=lomo.p.operario, variance_reason="yo")
        assert not r.success and r.error_code == "SEGREGATION_OF_DUTIES"

    def test_autorizador_sin_el_permiso_no_alcanza(self, lomo):
        r = _ejecutar(lomo, lomo.orden(), salidas=lomo.salidas(*self.POBRE),
                      uc=_uc({lomo.p.gerente: ()}),
                      variance_authorizer_user_id=lomo.p.gerente, variance_reason="dale")
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_la_autorizacion_exige_motivo(self, lomo):
        uc = _uc({lomo.p.gerente: (MeatProcessingPermissions.YIELD_OVERRIDE,)})
        r = _ejecutar(lomo, lomo.orden(), salidas=lomo.salidas(*self.POBRE), uc=uc,
                      variance_authorizer_user_id=lomo.p.gerente, variance_reason="   ")
        assert not r.success and r.error_code == "YIELD_AUTHORIZATION_REQUIRED"

    def test_dentro_de_tolerancia_no_pide_nada(self, lomo):
        r = _ejecutar(lomo, lomo.orden())
        assert r.success and r.data["out_of_tolerance"] is False


class TestValidacionAntesDeMutar:
    def test_sin_costo_de_entrada_no_se_consume_nada(self, lomo):
        oid = lomo.orden()
        lomo.conn.execute("DELETE FROM product_cost")
        lomo.conn.commit()
        r = _ejecutar(lomo, oid)
        assert not r.success and r.error_code == "MISSING_INPUT_COST"
        assert lomo.p.saldo(lomo.lomo) == Decimal("20")          # nada se consumió
        assert lomo.p.reservado(lomo.lomo) == Decimal("10")      # la reserva sigue viva
        assert _estado(lomo, oid) is ProcessingOrderStatus.RELEASED

    def test_sin_base_de_reparto_falla_sin_consumir(self, lomo):
        oid = lomo.orden()
        lomo.conn.execute("DELETE FROM product_price WHERE product_id=?", (lomo.chuleta,))
        lomo.conn.commit()
        r = _ejecutar(lomo, oid)
        assert not r.success and r.error_code == "COST_ALLOCATION_FAILED"
        assert lomo.p.saldo(lomo.chuleta) == Decimal("0")
        assert lomo.p.reservado(lomo.lomo) == Decimal("10")

    def test_un_producto_ajeno_a_la_definicion_se_rechaza(self, lomo):
        r = _ejecutar(lomo, lomo.orden(), salidas={new_uuid(): "3"})
        assert not r.success and r.error_code == "INVALID_EXECUTION"

    def test_sin_salida_productiva_no_se_ejecuta(self, lomo):
        r = _ejecutar(lomo, lomo.orden(), salidas=lomo.salidas("0", "0", "10"))
        assert not r.success and r.error_code == "INVALID_EXECUTION"

    def test_una_orden_cerrada_no_se_vuelve_a_ejecutar(self, lomo):
        oid = lomo.orden()
        assert _ejecutar(lomo, oid).success
        r = _ejecutar(lomo, oid)
        assert not r.success and r.error_code == "INVALID_STATE"

    def test_una_orden_sin_preparar_no_se_ejecuta(self, lomo):
        r = _ejecutar(lomo, lomo.p.orden(ProcessType.DISASSEMBLY, lomo.lomo, "10"))
        assert not r.success and r.error_code == "INVALID_STATE"

    def test_orden_inexistente(self, lomo):
        r = _ejecutar(lomo, new_uuid())
        assert not r.success and r.error_code == "ORDER_NOT_FOUND"


class TestReanudable:
    def test_reintentar_tras_un_fallo_continua_sin_duplicar(self, lomo):
        """El primer intento consume la entrada y se cae al recibir una
        salida; el segundo sigue donde quedó sin volver a consumir ni recibir."""
        real = execution_ports_factory()
        fallas = {"quedan": 1}

        class _Receptor:
            def __init__(self, receptor):
                self._r = receptor
                self.last_error = None

            def __getattr__(self, nombre):
                return getattr(self._r, nombre)

            def post_output(self, **kwargs):
                if fallas["quedan"]:
                    fallas["quedan"] -= 1
                    self.last_error = "Inventario no respondió"
                    return None
                return self._r.post_output(**kwargs)

        def con_falla(connection, order, actor, reason=None):
            puertos = real(connection, order, actor, reason)
            puertos.receipt = _Receptor(puertos.receipt)
            return puertos

        oid = lomo.orden()
        primero = _ejecutar(lomo, oid, uc=_uc(ports_factory=con_falla))
        assert not primero.success
        assert lomo.p.saldo(lomo.lomo) == Decimal("10")          # ya consumida

        segundo = _ejecutar(lomo, oid)
        assert segundo.success, segundo.message
        assert lomo.p.saldo(lomo.lomo) == Decimal("10")          # NO se duplicó
        assert lomo.p.saldo(lomo.chuleta) == Decimal("6")
        assert lomo.p.saldo(lomo.recorte) == Decimal("3")
        assert _estado(lomo, oid) is ProcessingOrderStatus.CLOSED


class TestRegistroPorSalida:
    """§13: el resultado por salida es un registro consultable. El costo de
    cada salida viene de Costos."""

    def test_lo_ejecutado_queda_en_el_registro_de_la_sucursal(self, lomo):
        from backend.application.meat_processing.queries.meat_processing_records_query_service import (  # noqa: E501
            MeatProcessingRecord,
            MeatProcessingRecordsQueryService,
        )

        _ejecutar(lomo, lomo.orden())
        pagina = MeatProcessingRecordsQueryService(lomo.conn).list_records(
            lomo.p.branch, MeatProcessingRecord.OUTPUT_RESULTS)
        assert pagina.total == 3
        merma = [f for f in pagina.rows if f["output_type"] == "WASTE"][0]
        assert Decimal(str(merma["allocated_cost"])) == Decimal("0")
        assert merma["output_lot_id"] is None
        buenos = [f for f in pagina.rows if f["output_type"] != "WASTE"]
        assert all(f["output_lot_id"] and Decimal(str(f["allocated_cost"])) > 0
                   for f in buenos)
        assert sum(Decimal(str(f["allocated_cost"])) for f in pagina.rows) == Decimal("800.00")

    def test_el_registro_no_cruza_sucursales(self, lomo):
        from backend.application.meat_processing.queries.meat_processing_records_query_service import (  # noqa: E501
            MeatProcessingRecord,
            MeatProcessingRecordsQueryService,
        )

        _ejecutar(lomo, lomo.orden())
        pagina = MeatProcessingRecordsQueryService(lomo.conn).list_records(
            new_uuid(), MeatProcessingRecord.OUTPUT_RESULTS)
        assert pagina.total == 0
