# migrations/standalone/257_sale_lines_unified_read_view.py
"""Corte de Ventas paso 3: fuente única de lectura para las LÍNEAS de venta.

Gemela de `v_ventas_unificada` (migración 256), al nivel de línea:

    v_detalles_venta_unificada = sale_lines (canónico)
                               ∪ detalles_venta de ventas aún no migradas

CORRIGE UNA OBJECIÓN MÍA ANTERIOR
La 256 dejó fuera las líneas argumentando que unificar daría "COGS 0 en
silencio" para las ventas canónicas, porque `sale_lines` no guarda costo.
Esa objeción era INCORRECTA, y se comprobó leyendo el código:

  * NINGÚN archivo productivo escribe `detalles_venta.costo_unitario_real`.
    Sólo aparece en SELECTs. La columna lleva vacía desde siempre.
  * Por eso todos los lectores de rentabilidad la envuelven en un COALESCE
    cuyo segundo término es `product_cost.average_cost` — una tabla CANÓNICA
    (ver `COST_LINE`/`_COST_JOIN` en `bi_sales_query_service.py` y
    `_COSTO_LINE` en `analytics_engine.py`).

Es decir: el COGS de TODAS las ventas, legacy incluidas, ya sale hoy de
`product_cost`. Una línea canónica con costo desconocido recorre exactamente
el mismo camino que una línea legacy, que es el caso real del 100% de ellas.
Unificar no pierde fidelidad: la iguala.

Lo que sí sigue siendo cierto es que ninguna de las dos rutas captura el costo
EN EL MOMENTO de la venta — usan el promedio actual. Eso es una imprecisión
preexistente del modelo de rentabilidad, no algo que introduzca esta vista, y
su arreglo (capturar costo en la línea canónica) queda pendiente y anotado.

COSTO EXPUESTO POR LA VISTA
Para las líneas respaldadas por la 255 se recupera del `product_snapshot`, que
guardó el `costo_unitario_real` de la fila legacy. Para el resto, 0 — que es
lo que dispara el fallback canónico del lector, igual que hoy.

CRITERIO DE ELIMINACIÓN
El mismo que la 256: cuando el ratchet mida 0 escritores legacy, el brazo
legacy sobra y la vista se reduce a `sale_lines` antes de desaparecer.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.257")

VIEW_NAME = "v_detalles_venta_unificada"

_DDL = f"""
CREATE VIEW {VIEW_NAME} AS
    SELECT
        l.id                                    AS id,
        l.sale_id                               AS venta_id,
        l.product_id                            AS producto_id,
        json_extract(l.product_snapshot, '$.name')          AS nombre,
        CAST(l.quantity AS REAL)                AS cantidad,
        CAST(l.unit_price AS REAL)              AS precio_unitario,
        CAST(l.discount_total AS REAL)          AS descuento,
        (CAST(l.quantity AS REAL) * CAST(l.unit_price AS REAL)
            - CAST(l.discount_total AS REAL))   AS subtotal,
        l.quantity_unit                         AS unidad,
        l.lot_reference                         AS batch_id,
        COALESCE(CAST(json_extract(l.product_snapshot, '$.unit_cost') AS REAL), 0)
                                                AS costo_unitario_real,
        'canonical'                             AS origen
    FROM sale_lines l

    UNION ALL

    SELECT
        d.id, d.venta_id, d.producto_id, d.nombre, d.cantidad,
        d.precio_unitario, d.descuento, d.subtotal, d.unidad, d.batch_id,
        COALESCE(d.costo_unitario_real, 0), 'legacy'
    FROM detalles_venta d
    WHERE d.venta_id NOT IN (SELECT id FROM sales)
"""


def _relation_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name=? AND type IN ('table','view')",
        (name,),
    ).fetchone() is not None


def run(conn) -> None:
    for required in ("detalles_venta", "sale_lines", "sales"):
        if not _relation_exists(conn, required):
            logger.info("257: falta `%s`; no se crea la vista.", required)
            return

    conn.execute(f"DROP VIEW IF EXISTS {VIEW_NAME}")
    conn.execute(_DDL)
    conn.commit()
    logger.info("257: vista %s creada (canónico ∪ legacy no migrado).", VIEW_NAME)


up = run
