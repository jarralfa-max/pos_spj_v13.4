"""
migrations/standalone/067_fix_branch_inventory_unique.py

Problema: branch_inventory tiene UNIQUE(branch_id, product_id, batch_id).
Cuando batch_id IS NULL, SQLite trata cada NULL como distinto → nunca hay
conflicto → los UPSERT por (product_id, branch_id) acumulan filas duplicadas
en lugar de actualizar, rompiendo el stock en tiempo real.

Solución:
  1. Consolidar filas duplicadas (product_id, branch_id, batch_id IS NULL)
     sumando sus cantidades.
  2. Agregar índice UNIQUE(product_id, branch_id) WHERE batch_id IS NULL
     para detección de conflicto directa.

El código de servicio ya usa manual UPDATE+INSERT en lugar de ON CONFLICT,
así que este índice refuerza integridad sin romper nada.
"""
import logging

logger = logging.getLogger("spj.migrations")


def run(conn):
    # 1. Consolidar duplicados: sumar quantity de filas con mismo (product_id, branch_id) y batch_id NULL
    try:
        dupes = conn.execute("""
            SELECT product_id, branch_id, SUM(quantity) AS total_qty
            FROM branch_inventory
            WHERE batch_id IS NULL
            GROUP BY product_id, branch_id
            HAVING COUNT(*) > 1
        """).fetchall()

        for row in dupes:
            pid, bid, total = row[0], row[1], row[2]
            # Borrar todas las filas duplicadas para este par
            conn.execute("""
                DELETE FROM branch_inventory
                WHERE product_id = ? AND branch_id = ? AND batch_id IS NULL
            """, (pid, bid))
            # Reinsertar una sola fila consolidada
            conn.execute("""
                INSERT INTO branch_inventory (product_id, branch_id, quantity, batch_id, updated_at)
                VALUES (?, ?, ?, NULL, datetime('now'))
            """, (pid, bid, max(0.0, float(total or 0))))

        if dupes:
            logger.info("branch_inventory: %d pares consolidados.", len(dupes))

        conn.commit()
    except Exception as e:
        logger.warning("Consolidación branch_inventory: %s", e)

    # 2. Índice único parcial (product_id, branch_id) donde batch_id IS NULL
    # Permite detección de conflicto sin tocar filas con lote asignado.
    try:
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_branch_inv_no_batch
            ON branch_inventory(product_id, branch_id)
            WHERE batch_id IS NULL
        """)
        conn.commit()
        logger.info("Índice uq_branch_inv_no_batch creado/verificado.")
    except Exception as e:
        logger.warning("Índice branch_inventory: %s", e)
