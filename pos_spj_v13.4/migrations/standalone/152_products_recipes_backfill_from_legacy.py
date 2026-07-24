# migrations/standalone/152_products_recipes_backfill_from_legacy.py
"""PROD-19 paso 4 — backfill de recetas legacy → recipe/recipe_version canónico.

Copia (idempotente, aditiva) los dos sistemas de recetas legacy reales al esquema
canónico versionado (`recipes` → `recipe_versions` v1 → `recipe_components` +
`recipe_outputs`):

    recetas + receta_componentes                   (español)
    product_recipes + product_recipe_components     (inglés; usado por
                                                     product_catalog_query_service)

Reglas:
- **Idempotente**: ids legacy preservados como PK canónica (INSERT OR IGNORE);
  la versión v1 se de-duplica por UNIQUE(recipe_id, version_number).
- **Decimal-only**: cantidades/porcentajes REAL → string Decimal (nunca REAL).
- **Aditivo**: el legacy queda intacto; sus lectores viven hasta el DROP (PROD-19
  paso 10). En una DB fresca las tablas están vacías → no-op (bootstrap limpio).
- Una receta legacy (sin versiones) → una `recipe_versions` v1 (ACTIVE si activa,
  DRAFT si no); el producto base es el `recipe_outputs` de la versión.

Sistemas legacy NO cubiertos aquí (concepto distinto, otro backfill/contexto):
`product_recipes_abarrotes` (ratios), `componentes_producto` (compuesto),
`paquetes_componentes` (→ bundles, PROD-14), `recipe_dependency_graph` (grafo).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.152")


def run(conn) -> None:
    stats = {
        "recetas": _backfill_recetas(conn),
        "product_recipes": _backfill_product_recipes(conn),
    }
    conn.commit()
    logger.info("152: backfill recetas → canónico %s", stats)


# ── helpers ────────────────────────────────────────────────────────────────
def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _cols(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _dec(value, default="0") -> str:
    if value in (None, ""):
        return default
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.0001")))
    except (InvalidOperation, ValueError):
        return default


def _unit(value) -> str:
    v = str(value or "").strip().upper()
    return v or "PZA"


def _ensure_version(conn, recipe_id: str, active: int) -> str:
    """Crea (idempotente) la versión v1 de una receta y devuelve su id."""
    row = conn.execute(
        "SELECT id FROM recipe_versions WHERE recipe_id=? AND version_number=1",
        (recipe_id,)).fetchone()
    if row:
        return row[0]
    status = "ACTIVE" if active else "DRAFT"
    vid = new_uuid()
    conn.execute(
        "INSERT OR IGNORE INTO recipe_versions (id, recipe_id, version_number, status) "
        "VALUES (?,?,1,?)", (vid, recipe_id, status))
    return conn.execute(
        "SELECT id FROM recipe_versions WHERE recipe_id=? AND version_number=1",
        (recipe_id,)).fetchone()[0]


def _insert_recipe(conn, *, rid: str, product_id: str, recipe_type: str, name: str,
                   active: int) -> int:
    return conn.execute(
        "INSERT OR IGNORE INTO recipes (id, product_id, recipe_type, name, active) "
        "VALUES (?,?,?,?,?)",
        (rid, product_id, recipe_type, name, 1 if active else 0)).rowcount or 0


def _insert_output(conn, *, version_id: str, product_id: str, yield_pct) -> None:
    oid = f"{version_id}-out"
    conn.execute(
        "INSERT OR IGNORE INTO recipe_outputs (id, version_id, product_id, output_type, "
        "quantity, unit_id, expected_yield_pct, sequence) VALUES (?,?,?,?,?,?,?,0)",
        (oid, version_id, product_id, "MAIN", "1", "PZA",
         None if yield_pct in (None, "") else _dec(yield_pct)))


def _insert_component(conn, *, comp_id: str, version_id: str, component_product_id: str,
                      quantity, unit, scrap, sequence: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO recipe_components (id, version_id, component_product_id, "
        "quantity, unit_id, scrap_pct, sequence) VALUES (?,?,?,?,?,?,?)",
        (comp_id, version_id, component_product_id, _dec(quantity, "0"),
         _unit(unit), _dec(scrap, "0"), sequence))


# ── recetas + receta_componentes (español) ──────────────────────────────────
def _backfill_recetas(conn) -> int:
    if not _table_exists(conn, "recetas"):
        return 0
    cols = _cols(conn, "recetas")
    if "producto_base_id" not in cols:
        return 0
    rows = conn.execute(
        "SELECT id, nombre, tipo_receta, producto_base_id, activo, "
        "rendimiento_esperado_pct FROM recetas").fetchall()
    n = 0
    for rid, nombre, tipo, base_id, activo, rend in rows:
        if not rid or not base_id:
            continue
        rtype = str(tipo or "PROCESSING").strip().upper() or "PROCESSING"
        name = (nombre or f"Receta {str(rid)[:8]}")
        n += _insert_recipe(conn, rid=rid, product_id=base_id, recipe_type=rtype,
                            name=name, active=int(activo or 0))
        vid = _ensure_version(conn, rid, int(activo or 0))
        _insert_output(conn, version_id=vid, product_id=base_id, yield_pct=rend)
        _migrate_components(
            conn, version_id=vid, table="receta_componentes", fk="receta_id",
            recipe_id=rid, prod_col="producto_id", qty_col="cantidad",
            unit_col="unidad", scrap_col="merma_porcentaje")
    return n


# ── product_recipes + product_recipe_components (inglés) ─────────────────────
def _backfill_product_recipes(conn) -> int:
    if not _table_exists(conn, "product_recipes"):
        return 0
    cols = _cols(conn, "product_recipes")
    rows = conn.execute("SELECT * FROM product_recipes").fetchall()
    colnames = [d[0] for d in conn.execute("SELECT * FROM product_recipes LIMIT 0").description]
    n = 0
    for r in rows:
        d = dict(zip(colnames, r))
        rid = d.get("id")
        base_id = (d.get("output_product_id") or d.get("product_id")
                   or d.get("base_product_id") or d.get("piece_product_id"))
        if not rid or not base_id:
            continue
        active = int(d.get("is_active") if d.get("is_active") is not None
                     else d.get("activa") or 0)
        rtype = str(d.get("tipo_receta") or "PROCESSING").strip().upper() or "PROCESSING"
        name = d.get("nombre_receta") or f"Recipe {str(rid)[:8]}"
        n += _insert_recipe(conn, rid=rid, product_id=base_id, recipe_type=rtype,
                            name=name, active=active)
        vid = _ensure_version(conn, rid, active)
        _insert_output(conn, version_id=vid, product_id=base_id,
                       yield_pct=d.get("rendimiento_esperado_pct") or d.get("total_rendimiento"))
        _migrate_components(
            conn, version_id=vid, table="product_recipe_components", fk="recipe_id",
            recipe_id=rid, prod_col="component_product_id", qty_col="cantidad",
            unit_col="unidad", scrap_col="merma_pct")
    return n


def _migrate_components(conn, *, version_id: str, table: str, fk: str, recipe_id: str,
                        prod_col: str, qty_col: str, unit_col: str, scrap_col: str) -> None:
    if not _table_exists(conn, table):
        return
    cols = _cols(conn, table)
    if prod_col not in cols or fk not in cols:
        return
    qcol = qty_col if qty_col in cols else None
    ucol = unit_col if unit_col in cols else None
    scol = scrap_col if scrap_col in cols else None
    sel = ["id", prod_col,
           qcol or "0 AS _q", ucol or "'' AS _u", scol or "0 AS _s"]
    rows = conn.execute(
        f"SELECT {', '.join(sel)} FROM {table} WHERE {fk}=?", (recipe_id,)).fetchall()
    for seq, (cid, prod, qty, unit, scrap) in enumerate(rows):
        if not prod:
            continue
        comp_id = cid or new_uuid()
        _insert_component(conn, comp_id=comp_id, version_id=version_id,
                          component_product_id=prod, quantity=qty, unit=unit,
                          scrap=scrap, sequence=seq)


up = run
