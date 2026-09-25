"""273 — Contextos de COSTOS y CALIDAD, y los permisos que los operan.

1. Costos: `processing_cost_allocations`, sus líneas y `costing_outbox`. El
   costeo de producción deja de calcularse en Procesamiento.
2. Calidad: `quality_inspections` y `quality_outbox`. La liberación de outputs
   deja de hacerla Procesamiento.
3. El costo por salida que la Fase 10 (migración 270) guardaba en
   `processing_output_results` pasa a Costos, SIN perder historia: cada orden
   ya costeada ahí queda como una asignación en `processing_cost_allocations`
   (método RELATIVE_SALES_VALUE, el que usaba aquel código). No se emiten
   eventos: Precios ya proyectó ese costo entonces. Después se reconstruye
   `processing_output_results` sin las columnas de costo (patrón de la 165).
4. Permisos (`INSERT OR IGNORE`, no revoca nada):
   - `CALIDAD.inspeccion.ver` y `CALIDAD.inspeccion.decidir` a gerente, admin y
     system_owner; `CALIDAD.inspeccion.ver` al almacén. Decidir NO se da al rol
     que produce (y además, por usuario, quien produjo nunca decide).
   - `PRODUCCION.material.asignar` al almacén: preparar la orden (reservar sus
     insumos en Inventario) es parte de "almacén produce"; sin él, ninguna
     orden podría llegar a READY y por tanto liberarse.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from backend.infrastructure.db.schema.costing_schema import create_costing_schema
from backend.infrastructure.db.schema.quality_schema import create_quality_schema
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.273")

_GRANTS = {
    "system_owner": [("CALIDAD", "inspeccion.ver"), ("CALIDAD", "inspeccion.decidir")],
    "admin": [("CALIDAD", "inspeccion.ver"), ("CALIDAD", "inspeccion.decidir")],
    "gerente": [("CALIDAD", "inspeccion.ver"), ("CALIDAD", "inspeccion.decidir")],
    "almacen": [("CALIDAD", "inspeccion.ver"), ("PRODUCCION", "material.asignar")],
}


def _existe(conn, tabla: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (tabla,)).fetchone() is not None


_COST_COLUMNS = ("input_unit_cost", "unit_price", "allocated_cost", "unit_cost")
_CENT = Decimal("0.01")


def _columnas(conn, tabla: str) -> list[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{tabla}")').fetchall()]


def _d(value) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else Decimal("0")


def _move_output_costs_to_costing(conn) -> int:
    """Cada orden con costo en `processing_output_results` y sin asignación en
    Costos queda como una asignación histórica de Costos."""
    if not _existe(conn, "processing_output_results") or \
            "allocated_cost" not in _columnas(conn, "processing_output_results"):
        return 0
    movidas = 0
    ordenes = [r[0] for r in conn.execute(
        "SELECT DISTINCT processing_order_id FROM processing_output_results r"
        " WHERE NOT EXISTS (SELECT 1 FROM processing_cost_allocations a"
        "                   WHERE a.processing_order_id = r.processing_order_id)").fetchall()]
    for orden_id in ordenes:
        filas = conn.execute(
            "SELECT product_id, output_type, input_product_id, input_weight, input_unit_cost,"
            " actual_weight, unit_price, allocated_cost, unit_cost, input_lot_id, output_lot_id,"
            " created_at FROM processing_output_results WHERE processing_order_id=?",
            (orden_id,)).fetchall()
        if not any(_d(f[7]) > 0 or _d(f[4]) > 0 for f in filas):
            continue                        # nunca se costeó: nada que mover
        orden = conn.execute(
            "SELECT branch_id, process_type, COALESCE(closed_by_user_id, created_by_user_id)"
            " FROM processing_orders WHERE id=?", (orden_id,)).fetchone()
        if orden is None:
            continue
        primera = filas[0]
        costo_entrada = (_d(primera[3]) * _d(primera[4])).quantize(_CENT, ROUND_HALF_UP)
        merma = sum((_d(f[7]) for f in filas if f[1] in ("WASTE", "LOSS")), Decimal("0"))
        asignacion = new_uuid()
        conn.execute(
            "INSERT INTO processing_cost_allocations (id, operation_id, processing_order_id,"
            " source_module, branch_id, process_type, method, currency_code, input_cost_total,"
            " output_value_total, waste_value_total, created_by_user_id, created_at)"
            " VALUES (?,?,?,?,?,?,'RELATIVE_SALES_VALUE','MXN',?,?,?,?,?)",
            (asignacion, new_uuid(), orden_id, "meat_processing", orden[0], orden[1],
             str(costo_entrada), str(costo_entrada - merma), str(merma),
             orden[2] or "migration_273", primera[11]))
        conn.execute(
            "INSERT INTO processing_cost_allocation_lines (id, allocation_id, line_kind,"
            " product_id, output_type, lot_id, quantity, unit_price, basis_value,"
            " allocated_cost, unit_cost) VALUES (?,?,'INPUT',?,NULL,?,?,NULL,'0',?,?)",
            (new_uuid(), asignacion, primera[2], primera[9], str(_d(primera[3])),
             str(costo_entrada), str(_d(primera[4]))))
        for f in filas:
            conn.execute(
                "INSERT INTO processing_cost_allocation_lines (id, allocation_id, line_kind,"
                " product_id, output_type, lot_id, quantity, unit_price, basis_value,"
                " allocated_cost, unit_cost) VALUES (?,?,'OUTPUT',?,?,?,?,?,?,?,?)",
                (new_uuid(), asignacion, f[0], f[1], f[10], str(_d(f[5])),
                 None if f[6] in (None, "") else str(f[6]),
                 str(_d(f[5]) * _d(f[6])) if f[6] not in (None, "") else "0",
                 str(_d(f[7])), str(_d(f[8]))))
        movidas += 1
    return movidas


def _rebuild_output_results_without_costs(conn) -> bool:
    if not _existe(conn, "processing_output_results"):
        return False
    viejas = _columnas(conn, "processing_output_results")
    if not any(c in viejas for c in _COST_COLUMNS):
        return False
    from backend.infrastructure.db.schema import meat_processing_schema as esquema

    conn.execute("ALTER TABLE processing_output_results RENAME TO processing_output_results__old")
    for indice in esquema._INDEXES_OUTPUT_RESULTS:
        conn.execute(f"DROP INDEX IF EXISTS {indice.split('EXISTS ')[1].split(' ')[0]}")
    esquema.create_meat_processing_output_results_schema(conn)
    comunes = [c for c in _columnas(conn, "processing_output_results") if c in viejas]
    lista = ", ".join(f'"{c}"' for c in comunes)
    conn.execute(f"INSERT INTO processing_output_results ({lista}) "
                 f"SELECT {lista} FROM processing_output_results__old")
    conn.execute("DROP TABLE processing_output_results__old")
    return True


def run(conn) -> None:
    create_costing_schema(conn)
    create_quality_schema(conn)
    movidas = _move_output_costs_to_costing(conn)
    reconstruida = _rebuild_output_results_without_costs(conn)
    conn.commit()
    logger.info("273: costos históricos movidos a Costos=%s; resultados sin columnas de "
                "costo=%s", movidas, reconstruida)
    concedidos = 0
    if _existe(conn, "roles") and _existe(conn, "rol_permisos"):
        for rol, permisos in _GRANTS.items():
            fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                                (rol,)).fetchone()
            if fila is None:
                continue
            for modulo, accion in permisos:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                    " VALUES (?,?,?,?,1)", (new_uuid(), str(fila[0]), modulo, accion))
                concedidos += max(cur.rowcount or 0, 0)
    conn.commit()
    logger.info("273: Costos y Calidad listos; %s permisos concedidos.", concedidos)


up = run
