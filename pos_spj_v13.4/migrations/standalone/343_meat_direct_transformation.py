"""343 — Transformación directa y bloqueos del despiece (auditoría de
Producción cárnica 32cfbf, 2026-10-16).

Medido en una copia de la base real: «Pollo Entero» tiene un perfil de
rendimiento ACTIVO (8 salidas, 100 %) y 132.68 kg en existencia, y aun así no
se podía despiezar: (a) la política exigía esquema de corte (corregido en
código: el perfil manda); (b) los 4 lotes de compra nacieron «pendiente de
inspección» aunque ningún producto exige inspección, y Producción sólo reserva
lotes liberados; (c) ningún almacén estaba marcado «Producción» (configuración
del usuario, no se toca aquí).

1. `direct_transformations`: bitácora idempotente de la acción única.
2. `processing_output_results.weight_source` / `estimate_reason`: una salida
   cuyo peso real se tomó de lo esperado queda marcada ESTIMADO con su motivo.
3. Lotes de COMPRA que siguen «pendiente de inspección» sin que su producto la
   exija (misma regla que la recepción: su perfil de calidad pide inspección) y
   sin ninguna inspección registrada en Calidad → LIBERADO.
4. `PRODUCCION.transformacion_directa.ejecutar` a los roles que ya pueden
   iniciar órdenes (`PRODUCCION.orden.iniciar`).

Idempotente.
"""

from __future__ import annotations

import logging
import sqlite3

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.343")


def _table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def _columns(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def run(conn) -> None:
    from backend.infrastructure.db.schema.meat_processing_schema import (
        create_meat_processing_direct_transformation_schema,
    )

    if _table(conn, "processing_orders"):
        create_meat_processing_direct_transformation_schema(conn)

    if _table(conn, "processing_output_results"):
        columnas = _columns(conn, "processing_output_results")
        if "weight_source" not in columnas:
            conn.execute("ALTER TABLE processing_output_results ADD COLUMN weight_source"
                         " TEXT NOT NULL DEFAULT 'CAPTURED'")
        if "estimate_reason" not in columnas:
            conn.execute("ALTER TABLE processing_output_results ADD COLUMN estimate_reason TEXT")

    liberados = _release_uninspected_purchase_lots(conn)
    sembrados = _seed_permission(conn)
    conn.commit()
    logger.info("343: transformación directa; %s lote(s) de compra liberados; permiso a %s rol(es).",
                liberados, sembrados)


def _release_uninspected_purchase_lots(conn) -> int:
    if not _table(conn, "inventory_lots"):
        return 0
    # La MISMA regla con la que la recepción decide si el renglón entra a
    # inspección (`PurchaseReceiptHandler._requires_inspection`): el perfil de
    # calidad del producto pide inspección.
    exige = ["0"]
    if _table(conn, "product_quality_profiles"):
        exige = ["EXISTS (SELECT 1 FROM product_quality_profiles q WHERE q.product_id = l.product_id"
                 " AND COALESCE(q.inspection_required, 0) = 1)"]
    abierta = ""
    if _table(conn, "quality_inspections"):
        # Conservador: cualquier inspección registrada para el lote (abierta o
        # decidida) deja la decisión a Calidad.
        abierta = (" AND NOT EXISTS (SELECT 1 FROM quality_inspections i"
                   " WHERE i.lot_id = l.id)")
    cur = conn.execute(
        "UPDATE inventory_lots SET quality_status = 'RELEASED' WHERE id IN ("
        " SELECT l.id FROM inventory_lots l"
        " WHERE l.origin_type = 'PURCHASE' AND l.quality_status = 'PENDING_INSPECTION'"
        f" AND NOT ({' OR '.join(exige)}){abierta})")
    return cur.rowcount or 0


def _seed_permission(conn) -> int:
    if not (_table(conn, "rol_permisos") and _table(conn, "roles")):
        return 0
    try:
        roles = [r[0] for r in conn.execute(
            "SELECT DISTINCT rol_id FROM rol_permisos WHERE modulo = 'PRODUCCION'"
            " AND accion = 'orden.iniciar' AND COALESCE(permitido, 1) = 1")]
    except sqlite3.OperationalError:
        return 0
    sembrados = 0
    for rol_id in roles:
        existe = conn.execute(
            "SELECT 1 FROM rol_permisos WHERE rol_id = ? AND modulo = 'PRODUCCION'"
            " AND accion = 'transformacion_directa.ejecutar'", (rol_id,)).fetchone()
        if existe:
            continue
        conn.execute("INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                     " VALUES (?, ?, 'PRODUCCION', 'transformacion_directa.ejecutar', 1)",
                     (new_uuid(), rol_id))
        sembrados += 1
    return sembrados
