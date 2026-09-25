"""§8/§21/§25 — genealogía MUCHOS a MUCHOS: cada lote producido queda ligado en
Inventario a CADA lote de entrada que la orden consumió, y la pantalla de
Trazabilidad los muestra todos.

- Formulación (mezcla de res y cerdo), con el cerdo repartido entre dos lotes.
- Despiece (canal bovina): un lote de entrada → varios lotes de salida.
"""
from __future__ import annotations

from backend.application.meat_processing.queries.lot_traceability_query_service import (
    MeatLotTraceabilityQueryService,
)
from backend.domain.meat_processing.enums import ProcessType
from tests.integration.meat_processing._generic_plant import Planta, build_db


def _padres(conn, hijo):
    return {r[0] for r in conn.execute(
        "SELECT parent_lot_id FROM inventory_traceability_link WHERE child_lot_id=?",
        (hijo,)).fetchall()}


def test_a_formulation_output_lot_has_every_consumed_lot_as_parent():
    conn = build_db()
    p = Planta(conn)
    res = p.producto("Carne de res", lote=True)
    cerdo = p.producto("Carne de cerdo", lote=True)
    mezcla = p.producto("Mezcla molida", lote=True)
    p.receta(mezcla, [(res, "0.6"), (cerdo, "0.4")])
    p.costo(res, "130"); p.costo(cerdo, "90")
    lote_res = p.existencia(res, "30", lote="RES-1", vence="2031-06-01")
    cerdo_a = p.existencia(cerdo, "3", lote="CER-A", vence="2031-01-01")
    cerdo_b = p.existencia(cerdo, "20", lote="CER-B", vence="2031-07-01")

    oid = p.lista(ProcessType.MIXING, mezcla, "20")          # 12 res, 8 cerdo (3 + 5)
    assert p.ejecutar(oid, {mezcla: "20"}).success

    lote_mezcla = p.salida(oid, mezcla).lot_id
    assert _padres(conn, lote_mezcla) == {lote_res, cerdo_a, cerdo_b}

    recorrido = MeatLotTraceabilityQueryService(conn).trace(p.branch, lote_mezcla)
    assert {e.lot_id for e in recorrido.inputs} == {lote_res, cerdo_a, cerdo_b}
    pesos = {e.lot_id: e.weight for e in recorrido.inputs}
    assert (pesos[cerdo_a], pesos[cerdo_b]) == ("3", "5")


def test_a_disassembly_input_lot_is_parent_of_every_output_lot():
    conn = build_db()
    p = Planta(conn)
    especie = p.especie("Bovino")
    canal = p.producto("Canal bovina", lote=True, especie=especie)
    pierna = p.producto("Pierna", lote=True, especie=especie)
    espaldilla = p.producto("Espaldilla", lote=True, especie=especie)
    p.despiece(canal, [(pierna, "MAIN_PRODUCT", "0.5"), (espaldilla, "CO_PRODUCT", "0.5")],
               especie=especie)
    p.costo(canal, "100"); p.precio(pierna, "200"); p.precio(espaldilla, "150")
    lote_canal = p.existencia(canal, "100", lote="CANAL-7", vence="2031-01-01")

    oid = p.lista(ProcessType.DISASSEMBLY, canal, "100")
    assert p.ejecutar(oid, {pierna: "50", espaldilla: "50"}).success

    hijos = {p.salida(oid, pierna).lot_id, p.salida(oid, espaldilla).lot_id}
    assert len(hijos) == 2
    for hijo in hijos:
        assert _padres(conn, hijo) == {lote_canal}
