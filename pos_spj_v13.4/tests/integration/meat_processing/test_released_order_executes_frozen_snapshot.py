"""§2/§25 — una orden liberada ejecuta la definición CONGELADA al prepararla.

Canal bovina: después de liberar la orden, Productos cambia los rendimientos del
esquema de corte y hasta lo retira. La orden ya no lo lee: ejecuta la foto.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from backend.application.meat_processing.queries.processing_order_execution_query_service import (
    ProcessingOrderExecutionQueryService,
)
from backend.domain.meat_processing.enums import ProcessType
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from tests.integration.meat_processing._generic_plant import Planta, build_db


@pytest.fixture()
def canal():
    conn = build_db()
    p = Planta(conn)
    bovino = p.especie("Bovino")
    datos = {
        "p": p,
        "canal": p.producto("Canal bovina", lote=True, especie=bovino),
        "lomo": p.producto("Lomo bovino", lote=True, especie=bovino),
        "falda": p.producto("Falda", lote=True, especie=bovino),
        "hueso": p.producto("Hueso", especie=bovino),
    }
    datos["version"] = p.despiece(datos["canal"], [
        (datos["lomo"], "MAIN_PRODUCT", "0.30"), (datos["falda"], "CO_PRODUCT", "0.50"),
        (datos["hueso"], "WASTE", "0.20")], especie=bovino)
    p.costo(datos["canal"], "100")
    p.precio(datos["lomo"], "300"); p.precio(datos["falda"], "120")
    p.existencia(datos["canal"], "200", lote="CANAL-9", vence="2031-01-01")
    yield datos
    conn.close()


def _products_changes_under_the_order(conn, version, lomo):
    conn.execute("UPDATE cutting_outputs SET quantity='0.90' WHERE version_id=? AND product_id=?",
                 (version, lomo))
    conn.execute("UPDATE cutting_scheme_versions SET status='INACTIVE' WHERE id=?", (version,))
    conn.commit()


def test_the_released_order_executes_what_was_frozen(canal):
    p = canal["p"]
    oid = p.lista(ProcessType.DISASSEMBLY, canal["canal"], "100")
    _products_changes_under_the_order(p.conn, canal["version"], canal["lomo"])

    plan = ProcessingOrderExecutionQueryService(p.conn).plan(oid)
    esperado = {s["product_id"]: s["expected_weight"] for s in plan["outputs"]}
    assert esperado[canal["lomo"]] == Decimal("30.000")      # 0.30 congelado, no 0.90

    r = p.ejecutar(oid, {canal["lomo"]: "30", canal["falda"]: "50", canal["hueso"]: "20"})
    assert r.success, r.message
    # Con el 0.90 nuevo, 30 kg serían −66 %: fuera de tolerancia. No lo es.
    assert r.data["out_of_tolerance"] is False


def test_the_frozen_definition_carries_its_versions_and_who_froze_it(canal):
    p = canal["p"]
    oid = p.lista(ProcessType.DISASSEMBLY, canal["canal"], "100")
    foto = MeatProcessingUnitOfWork(p.conn).recipe_snapshots.get_by_order(oid)
    assert foto.is_frozen
    assert foto.cutting_scheme_version_id == canal["version"]
    assert foto.captured_by_user_id == p.operario
    assert {o.product_id for o in foto.outputs} == {canal["lomo"], canal["falda"],
                                                    canal["hueso"]}


def test_a_frozen_definition_is_never_replaced(canal):
    p = canal["p"]
    oid = p.lista(ProcessType.DISASSEMBLY, canal["canal"], "100")
    with MeatProcessingUnitOfWork(p.conn) as uow:
        foto = uow.recipe_snapshots.get_by_order(oid)
        otra = replace(foto, id=None, processing_order_id=None).frozen_for(
            processing_order_id=oid, captured_by_user_id=p.gerente,
            operation_id=foto.operation_id)
        with pytest.raises(MeatProcessingInvariantError):
            uow.recipe_snapshots.add(otra)
