# migrations/standalone/325_drop_legacy_products_schema.py
"""PROD-22 — retira el esquema legacy de Productos (§48.8).

Sustituye al script diferido `migrations/deferred/legacy_products_drop.py`, que
esperaba a que se cumplieran tres condiciones. Medidas el 2026-10-09:

1. El maestro canónico `products` es la fuente de verdad (11 productos en la
   base real; ninguno vive sólo en `productos`).
2. Cero lectores: el ratchet `test_products_legacy_consumers_ratchet.py` quedó
   con allowlist VACÍA (los últimos lectores eran código sin llamadores, borrado,
   y el microservicio WhatsApp, repuntado a `products`).
3. Las 19 tablas legacy y las 3 que las referencian por llave foránea
   (`branch_inventory`, `historial_precios`, `merma_log`) tienen 0 filas en la
   base real.

TODO O NADA, y nunca destruye datos: si alguna tabla objetivo tiene filas, o si
una tabla que NO está en la lista las referencia por llave foránea, la migración
no toca nada y lo deja en el log. Antes de las tablas quita las vistas y los
triggers que las nombran (en la base real: `v_productos_activos`,
`v_rentabilidad_productos`, `v_stock_critico`, `recetas_unificada`,
`vista_merma_resumen`, `trg_historial_precio_venta/compra`), que si no quedarían
rotas.

Las migraciones antiguas (m000, 030, 039, 043, 067) siguen creando estas tablas
en una base nueva; esta migración, que corre después, las retira. El resultado
final de un arranque limpio no las contiene.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("spj.migrations.325")

LEGACY_MASTER_TABLES = ("branch_products", "productos")
LEGACY_RECIPE_TABLES = (
    "recetas", "receta_componentes", "product_recipes", "product_recipe_components",
    "product_recipes_abarrotes", "componentes_producto", "paquetes_componentes",
    "recipe_dependency_graph",
)
LEGACY_YIELD_TABLES = (
    "rendimiento_pollo", "rendimiento_derivados", "meat_production_yields",
    "production_yield_analysis",
)
LEGACY_CLASSIFICATION_TABLES = ("cortes_caja_erp", "inventario_subproductos")
#: Tablas legacy que referencian `productos` por llave foránea (vacías y sin
#: lectores): si quedaran, cada INSERT con foreign_keys=ON fallaría.
LEGACY_DEPENDENT_TABLES = ("branch_inventory", "historial_precios", "merma_log")

TARGETS = (LEGACY_DEPENDENT_TABLES + LEGACY_MASTER_TABLES + LEGACY_RECIPE_TABLES
           + LEGACY_YIELD_TABLES + LEGACY_CLASSIFICATION_TABLES)


def _tables(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _referencing_tables(conn, existing: set[str], targets: set[str]) -> dict[str, str]:
    """Tabla externa → tabla objetivo que referencia."""
    found: dict[str, str] = {}
    for table in existing - targets:
        for fk in conn.execute(f"PRAGMA foreign_key_list('{table}')"):
            if fk[2] in targets:
                found[table] = fk[2]
    return found


def blockers(conn) -> list[str]:
    """Por qué no se puede retirar (vacío = se puede)."""
    existing = _tables(conn)
    present = [t for t in TARGETS if t in existing]
    reasons = [f"{t} tiene {n} fila(s)" for t in present
               for (n,) in [conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()] if n]
    reasons += [f"{table} referencia a {target}" for table, target in
                _referencing_tables(conn, existing, set(present)).items()]
    return reasons


def _dependent_objects(conn, present: list[str]) -> list[tuple[str, str]]:
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, present)) + r")\b", re.IGNORECASE)
    out = []
    for kind, name, tbl, sql in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE type IN ('view', 'trigger') AND sql IS NOT NULL"):
        if name in present:
            continue
        if tbl in present or pattern.search(sql or ""):
            out.append((kind, name))
    return out


def run(conn) -> list[str]:
    existing = _tables(conn)
    present = [t for t in TARGETS if t in existing]
    if not present:
        logger.info("325: no hay esquema legacy de Productos que retirar.")
        return []
    reasons = blockers(conn)
    if reasons:
        logger.warning("325: esquema legacy de Productos CONSERVADO, no se borra nada: %s",
                       "; ".join(reasons))
        return []
    for kind, name in _dependent_objects(conn, present):
        conn.execute(f'DROP {kind.upper()} IF EXISTS "{name}"')
    for table in present:  # TARGETS ya va de dependientes a maestro
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    conn.commit()
    logger.warning("325: esquema legacy de Productos retirado (%d tablas): %s",
                   len(present), ", ".join(present))
    return present


up = run
