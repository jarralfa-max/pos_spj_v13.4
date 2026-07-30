# migrations/standalone/168_replenishment_reorder_from_stock_minimo.py
"""PROD/INV corte de legacy — backfill de umbrales de reposición desde legacy.

Los lectores de "stock bajo" (reporte diario, health, alertas) comparaban
``productos.existencia <= productos.stock_minimo``. Al repuntarlos al modelo
canónico de disponibilidad, el umbral debe existir en canónico: esta migración
respalda, por cada producto activo con ``stock_minimo``, una **regla de
reposición global** (``branch_id=''``, ``warehouse_id=''``) con
``reorder_point = min_quantity = stock_minimo``, de modo que el conteo de stock
bajo por producto (disponible total ≤ reorder) sea equivalente al legacy.

Aditiva e idempotente: sólo crea la regla global cuando no existe ya para el
producto (UNIQUE product_id+branch_id+warehouse_id). No toca reglas por sucursal
existentes ni `productos`.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.168")


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def run(conn) -> None:
    if not (_table_exists(conn, "productos")
            and _table_exists(conn, "inventory_replenishment_rule")):
        logger.info("168: faltan tablas fuente/destino — omitido.")
        return

    rows = conn.execute(
        "SELECT id, stock_minimo FROM productos "
        "WHERE COALESCE(activo,1)=1 AND stock_minimo IS NOT NULL").fetchall()
    existing = {r[0] for r in conn.execute(
        "SELECT product_id FROM inventory_replenishment_rule "
        "WHERE branch_id='' AND warehouse_id=''").fetchall()}

    created = 0
    for pid, stock_min in rows:
        if pid in existing:
            continue
        threshold = str(stock_min if stock_min is not None else 0)
        conn.execute(
            "INSERT INTO inventory_replenishment_rule "
            "(id, product_id, branch_id, warehouse_id, min_quantity, reorder_point, "
            "active, created_at) VALUES (?,?,?,?,?,?,1, datetime('now'))",
            (new_uuid(), pid, "", "", threshold, threshold))
        existing.add(pid)
        created += 1

    conn.commit()
    logger.info("168: %d regla(s) global(es) de reposición respaldada(s) desde "
                "stock_minimo.", created)


up = run
