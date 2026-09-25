"""§14/§25 — toda identidad y toda operación que deja la ejecución es un UUIDv7
propio, nunca una cadena armada ("orden:consumo:producto"). Se revisa TODO lo
que una ejecución completa escribe, en todos los contextos que toca."""
from __future__ import annotations

from backend.application.costing.wiring import dispatch_costing_outbox
from backend.application.quality.wiring import dispatch_quality_outbox
from backend.domain.meat_processing.enums import ProcessType
from backend.shared.ids import is_uuidv7
from tests.integration.meat_processing._generic_plant import (
    Planta,
    build_db,
    bus_with_real_wiring,
)

#: (tabla, columnas de identidad/operación) que la ejecución llena.
TABLAS = {
    "processing_execution_steps": ("id", "operation_id"),
    "material_requirement_allocations": ("id", "inventory_reservation_id"),
    "material_consumptions": ("id", "operation_id", "inventory_operation_id"),
    "process_outputs": ("id", "operation_id", "inventory_operation_id", "lot_id"),
    "processing_recipe_snapshots": ("id", "operation_id"),
    "inventory_reservation": ("id", "operation_id"),
    "inventory_ledger": ("id", "operation_id"),
    "inventory_lots": ("id",),
    "inventory_traceability_link": ("id", "operation_id"),
    "processing_cost_allocations": ("id", "operation_id"),
    "costing_outbox": ("id", "event_id", "operation_id"),
    "quality_inspections": ("id", "operation_id", "decision_operation_id"),
    "quality_outbox": ("id", "event_id", "operation_id"),
}


def test_every_identity_written_by_a_full_execution_is_a_uuidv7():
    conn = build_db()
    p = Planta(conn)
    especie = p.especie("Pescado")
    entero = p.producto("Atún entero", lote=True, especie=especie)
    lomo = p.producto("Lomo de atún", lote=True, calidad=True, especie=especie)
    p.despiece(entero, [(lomo, "MAIN_PRODUCT", "1")], especie=especie)
    p.costo(entero, "200")
    p.existencia(entero, "40", lote="ATUN-1", vence="2031-01-01")
    bus = bus_with_real_wiring(conn)

    oid = p.lista(ProcessType.DISASSEMBLY, entero, "20")
    assert p.ejecutar(oid, {lomo: "20"},
                      dispatch=lambda c: dispatch_costing_outbox(c, bus)).success
    assert p.decidir_calidad(p.salida(oid, lomo).id, "RELEASED",
                             dispatch=lambda c: dispatch_quality_outbox(c, bus)).success

    malas = []
    revisadas = 0
    for tabla, columnas in TABLAS.items():
        for columna in columnas:
            for (valor,) in conn.execute(
                    f"SELECT {columna} FROM {tabla} WHERE {columna} IS NOT NULL"
                    f" AND {columna} <> ''").fetchall():
                revisadas += 1
                if not is_uuidv7(str(valor)):
                    malas.append((tabla, columna, valor))
    assert revisadas > 40
    assert malas == []


def test_retrying_a_step_reuses_its_operation_id_instead_of_building_one():
    from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
        MeatProcessingUnitOfWork,
    )

    conn = build_db()
    p = Planta(conn)
    especie = p.especie("Pescado")
    entero = p.producto("Atún entero", especie=especie)
    lomo = p.producto("Lomo de atún", especie=especie)
    p.despiece(entero, [(lomo, "MAIN_PRODUCT", "1")], especie=especie)
    p.existencia(entero, "40")
    oid = p.lista(ProcessType.DISASSEMBLY, entero, "20")
    pasos = MeatProcessingUnitOfWork(conn).execution_steps
    primero = pasos.begin(oid, "PRUEBA", oid)
    otra_vez = pasos.begin(oid, "PRUEBA", oid)
    assert primero.operation_id == otra_vez.operation_id and is_uuidv7(primero.operation_id)
