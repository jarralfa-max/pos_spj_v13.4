# migrations/standalone/256_sales_unified_read_view.py
"""Corte de Ventas paso 2: una sola fuente de LECTURA para la cabecera de venta.

El paso 1 (migración 255) metió el histórico legacy en el agregado canónico.
Pero repuntar los 49 lectores a `sales` todavía perdería datos: los 10
escritores legacy siguen creando filas en `ventas` que nunca llegan a `sales`.
Y dejarlos en `ventas` pierde lo contrario: las ventas del POS, que desde
SALES-19..22 nacen en `sales` y NO pasan por la tabla legacy.

Hoy, por tanto, NINGUNA de las dos tablas contiene todas las ventas. Esta
vista es la única fuente que sí las contiene:

    v_ventas_unificada = sales (canónico)
                       ∪ ventas cuyo id aún no está en sales

Adaptador de transición del §4, no arquitectura nueva: sólo traduce nombres de
columna, no implementa ninguna regla de negocio.

CRITERIO DE ELIMINACIÓN, explícito
Cuando los escritores legacy lleguen a 0 —lo mide
`tests/architecture/test_sales_persistence_split_ratchet.py`— esta vista deja
de tener segundo brazo y debe reducirse a `SELECT ... FROM sales`, y después
desaparecer cuando los lectores lean el agregado directamente.

ALCANCE: SÓLO CABECERA, Y ESTO NO ES PEREZA
No se unifican las LÍNEAS. El agregado canónico no guarda el costo unitario:
`sale_lines` no tiene columna de costo y el POS escribe
`product_snapshot={"name","sku"}` (ver `sales_pos_workspace.py`), mientras que
`detalles_venta.costo_unitario_real` sí lo tiene. Una vista de líneas
"unificada" devolvería COGS 0 para toda venta canónica, y los reportes de
margen saldrían mal en silencio — peor que la división actual, que al menos
es visible. Capturar el costo en la línea canónica es funcionalidad que falta
(§33 PASO 4) y es el prerrequisito para mover los lectores de rentabilidad.

Por eso los lectores que hacen JOIN a `detalles_venta` NO se repuntan todavía:
mezclar ingreso canónico con COGS legacy daría márgenes falsos.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.256")

VIEW_NAME = "v_ventas_unificada"

_DDL = f"""
CREATE VIEW {VIEW_NAME} AS
    SELECT
        s.id                                   AS id,
        s.sale_number                          AS folio,
        s.branch_id                            AS sucursal_id,
        COALESCE(u.usuario, s.cashier_user_id) AS usuario,
        s.customer_id                          AS cliente_id,
        CAST(s.gross_subtotal AS REAL)         AS subtotal,
        CAST(s.discount_total AS REAL)         AS descuento,
        CAST(s.total AS REAL)                  AS total,
        COALESCE((SELECT p.method FROM sale_payments p
                   WHERE p.sale_id = s.id
                   ORDER BY p.captured_at LIMIT 1), '')  AS forma_pago,
        CASE s.status
            WHEN 'COMPLETED' THEN 'completada'
            WHEN 'CANCELLED' THEN 'cancelada'
            ELSE LOWER(s.status)
        END                                    AS estado,
        s.created_at                           AS fecha,
        'canonical'                            AS origen
    FROM sales s
    LEFT JOIN usuarios u ON u.id = s.cashier_user_id

    UNION ALL

    SELECT
        v.id, v.folio, v.sucursal_id, v.usuario, v.cliente_id,
        v.subtotal, v.descuento, v.total, v.forma_pago, v.estado, v.fecha,
        'legacy'
    FROM ventas v
    WHERE v.id NOT IN (SELECT id FROM sales)
"""


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name=? AND type IN ('table','view')",
        (name,),
    ).fetchone() is not None


def run(conn) -> None:
    for required in ("ventas", "sales", "sale_payments", "usuarios"):
        if not _table_exists(conn, required):
            logger.info("256: falta `%s`; no se crea la vista.", required)
            return

    # Se recrea siempre: la definición puede cambiar (el brazo legacy
    # desaparece cuando los escritores migren) y una vista es metadato, no
    # datos — recrearla no puede perder nada.
    conn.execute(f"DROP VIEW IF EXISTS {VIEW_NAME}")
    conn.execute(_DDL)
    conn.commit()
    logger.info("256: vista %s creada (canónico ∪ legacy no migrado).", VIEW_NAME)


up = run
