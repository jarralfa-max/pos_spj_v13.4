"""272 — Procesamiento: definición congelada, reservas reales y bitácora de ejecución.

1. `processing_recipe_snapshots` (+ entradas y salidas): la definición
   productiva completa que la ejecución lee en exclusiva.
2. `material_requirement_allocations`: la reserva REAL de Inventario de cada
   requerimiento (reserva, lote y ubicación que eligió Inventario).
3. `processing_execution_steps`: la bitácora de la ejecución reanudable (cada
   paso guarda su `operation_id` UUIDv7 antes de llamar a otro contexto).
4. `process_outputs` admite `NOT_REQUIRED` (producto sin inspección): la
   restricción CHECK de SQLite no se altera, se reconstruye la tabla sin
   perder filas (patrón de la 165).
5. Órdenes ya liberadas con versiones capturadas: se reconstruye su foto desde
   ESAS versiones (inmutables en Productos), no desde las activas hoy.
6. Órdenes RELEASED que nunca reservaron ni consumieron vuelven a
   MATERIALS_PENDING: antes se liberaban sin reserva; ahora deben prepararse.
   Las que ya consumieron algo se dejan tal cual y se registran en el log.

Idempotente.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.infrastructure.db.schema.meat_processing_schema import (
    OUTPUT_QUALITY_STATUSES,
    create_meat_processing_execution_saga_schema,
    create_meat_processing_snapshot_schema,
)
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.272")


def _existe(conn, tabla: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (tabla,)).fetchone() is not None


def _rebuild_process_outputs(conn) -> bool:
    fila = conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"
                        " AND name='process_outputs'").fetchone()
    if fila is None or "NOT_REQUIRED" in (fila[0] or ""):
        return False
    viejo = fila[0]
    inicio = viejo.index("quality_status IN (")
    fin = viejo.index(")", inicio + len("quality_status IN ("))
    nuevo = viejo[:inicio] + f"quality_status IN ({OUTPUT_QUALITY_STATUSES}" + viejo[fin:]
    nuevo = nuevo.replace("process_outputs", "process_outputs__new", 1)
    columnas = ", ".join(f'"{r[1]}"' for r in conn.execute(
        'PRAGMA table_info("process_outputs")').fetchall())
    conn.execute(nuevo)
    conn.execute(f'INSERT INTO process_outputs__new ({columnas}) '
                 f'SELECT {columnas} FROM process_outputs')
    conn.execute("DROP TABLE process_outputs")
    conn.execute("ALTER TABLE process_outputs__new RENAME TO process_outputs")
    # Los índices se van con la tabla vieja: se recrean desde el esquema canónico.
    from backend.infrastructure.db.schema import meat_processing_schema as esquema
    for indice in esquema._INDEXES:
        if " ON process_outputs(" in indice:
            conn.execute(indice)
    return True


def _backfill_snapshots(conn) -> int:
    from backend.application.meat_processing.integrations.products_recipe_snapshot_adapter import (
        ProductsRecipeSnapshotAdapter,
    )
    from backend.infrastructure.db.repositories.meat_processing.recipe_snapshot_repository import (
        ProcessingRecipeSnapshotRepository,
    )
    if not _existe(conn, "recipes") and not _existe(conn, "cutting_schemes"):
        return 0
    adaptador = ProductsRecipeSnapshotAdapter(conn)
    repo = ProcessingRecipeSnapshotRepository(conn)
    hechas = 0
    for f in conn.execute(
            "SELECT o.id, o.process_type, o.target_product_id, o.recipe_version_id,"
            " o.cutting_scheme_version_id, o.yield_profile_version_id,"
            " COALESCE(o.released_by_user_id, o.created_by_user_id)"
            " FROM processing_orders o LEFT JOIN processing_recipe_snapshots s"
            " ON s.processing_order_id = o.id WHERE s.id IS NULL AND"
            " (o.recipe_version_id IS NOT NULL OR o.cutting_scheme_version_id IS NOT NULL"
            "  OR o.yield_profile_version_id IS NOT NULL)").fetchall():
        try:
            foto = adaptador.from_versions(
                target_product_id=f[2], process_type=f[1], recipe_version_id=f[3],
                cutting_scheme_version_id=f[4], yield_profile_version_id=f[5])
            if foto is None:
                continue
            repo.add(foto.frozen_for(processing_order_id=f[0], captured_by_user_id=f[6],
                                     operation_id=new_uuid()))
            hechas += 1
        except Exception:  # noqa: BLE001 — una orden no rompe la migración; se registra
            logger.exception("272: no se pudo reconstruir la definición de la orden %s", f[0])
    return hechas


def _unprepared_released_back_to_materials(conn) -> tuple[int, list[str]]:
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    regresadas, con_consumo = 0, []
    for (oid,) in conn.execute(
            "SELECT id FROM processing_orders WHERE status='RELEASED'").fetchall():
        consumio = conn.execute("SELECT 1 FROM material_consumptions WHERE processing_order_id=?"
                                " LIMIT 1", (oid,)).fetchone()
        reservo = conn.execute("SELECT 1 FROM material_requirement_allocations"
                               " WHERE processing_order_id=? LIMIT 1", (oid,)).fetchone()
        if consumio:
            con_consumo.append(oid)
            continue
        if reservo:
            continue
        conn.execute("UPDATE processing_orders SET status='MATERIALS_PENDING', updated_at=?"
                     " WHERE id=?", (ahora, oid))
        if _existe(conn, "meat_processing_audit_log"):
            columnas = {r[1] for r in conn.execute(
                "PRAGMA table_info(meat_processing_audit_log)").fetchall()}
            datos = {"id": new_uuid(), "entity_type": "ProcessingOrder", "entity_id": oid,
                     "action": "RETURNED_TO_PREPARATION", "user_id": None,
                     "operation_id": new_uuid(), "processing_order_id": oid,
                     "source_module": "migration_272",
                     "reason": "Liberada sin reserva real de Inventario; debe prepararse",
                     "after_json": json.dumps({"status": "MATERIALS_PENDING"}),
                     "occurred_at": ahora}
            usar = [c for c in datos if c in columnas]
            conn.execute(f"INSERT INTO meat_processing_audit_log ({','.join(usar)})"
                         f" VALUES ({','.join('?' * len(usar))})", [datos[c] for c in usar])
        regresadas += 1
    return regresadas, con_consumo


def run(conn) -> None:
    if not _existe(conn, "processing_orders"):
        logger.info("272: sin Procesamiento Cárnico; nada que hacer.")
        return
    create_meat_processing_snapshot_schema(conn)
    create_meat_processing_execution_saga_schema(conn)
    conn.commit()
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk:
        conn.execute("PRAGMA foreign_keys=OFF")
    try:
        reconstruida = _rebuild_process_outputs(conn)
        conn.commit()
        violaciones = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violaciones:
            raise RuntimeError(f"272: foreign_key_check falló: {violaciones}")
    finally:
        if fk:
            conn.execute("PRAGMA foreign_keys=ON")
    fotos = _backfill_snapshots(conn)
    regresadas, con_consumo = _unprepared_released_back_to_materials(conn)
    conn.commit()
    logger.info("272: outputs reconstruida=%s, fotos reconstruidas=%s, órdenes devueltas a "
                "preparación=%s, liberadas con consumo previo (sin tocar)=%s",
                reconstruida, fotos, regresadas, con_consumo or "ninguna")


up = run
