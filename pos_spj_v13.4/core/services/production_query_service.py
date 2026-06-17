# core/services/production_query_service.py — FASE 9
"""
ProductionQueryService — read-only SQL queries extracted from modulos/produccion.py.

All methods accept a db connection (or connection pool) and return plain Python
dicts/lists so the UI layer stays free of SQL.  No business logic lives here —
this is purely a data-access helper.

Methods:
  get_daily_kpis(db, branch_id, date=None)   → dict
  get_active_lotes_count(db)                 → int
  get_recetas_list(db)                       → list[dict]
  get_recipe_components(db, recipe_id)       → list[dict]
  get_historial_carnica(db, limit=100)       → list[dict]
  get_stock(db, product_id, sucursal_id)     → float
  get_stocks_for_products(db, product_ids, sucursal_id) → dict[int, float]
  get_recetas_for_combo(db)                  → list[dict]
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spj.services.production_query")
_TIPOS_VALIDOS = {"subproducto", "combinacion", "produccion"}


def _normalize_tipo_receta(value: Any, default: str = "subproducto") -> str:
    tipo = str(value or "").strip().lower()
    if tipo in _TIPOS_VALIDOS:
        return tipo
    return default


def _fetchone(db, sql: str, params=()):
    """Unified fetchone that works with both raw sqlite3 connections and pool wrappers."""
    try:
        if hasattr(db, "fetchone"):
            return db.fetchone(sql, params)
        row = db.execute(sql, params).fetchone()
        if row is None:
            return None
        if hasattr(row, "keys"):
            return row
        # sqlite3.Row is subscriptable but may not have named-column access
        # Convert to dict if column names are available
        try:
            return dict(row)
        except Exception:
            return row
    except Exception as exc:
        logger.debug("_fetchone: %s", exc)
        return None


def _fetchall(db, sql: str, params=()):
    """Unified fetchall that works with both raw connections and pool wrappers."""
    try:
        if hasattr(db, "fetchall"):
            return db.fetchall(sql, params)
        return db.execute(sql, params).fetchall()
    except Exception as exc:
        logger.debug("_fetchall: %s", exc)
        return []


# ── Schema detection ──────────────────────────────────────────────────────────

def _product_recipes_product_expr(db) -> str:
    """Return the column expression that holds the base product FK in product_recipes."""
    try:
        rows = _fetchall(db, "PRAGMA table_info(product_recipes)")
        cols = {r[1] if not hasattr(r, "keys") else r["name"] for r in rows}
        if "product_id" in cols:
            return "r.product_id"
        if "base_product_id" in cols:
            return "r.base_product_id"
    except Exception:
        pass
    return "NULL"


# ── Public API ────────────────────────────────────────────────────────────────

def get_daily_kpis(db, branch_id: int = 0, date: Optional[str] = None) -> Dict[str, Any]:
    """
    Return production KPIs for a given date (default: today).

    Primary source: production_batches + production_yield_analysis.
    Fallback: producciones + produccion_detalle (legacy schema).

    Returns dict with keys:
      producciones_hoy, kg_procesados, merma_dia, rendimiento, lotes_activos
    """
    date_expr = f"DATE('{date}')" if date else "DATE('now')"
    vals: Dict[str, Any] = {
        "producciones_hoy": 0,
        "kg_procesados":    0.0,
        "merma_dia":        0.0,
        "rendimiento":      0.0,
        "lotes_activos":    0,
    }

    # Primary: production_batches + production_yield_analysis
    # Use db.execute directly so missing tables raise and trigger the legacy fallback.
    try:
        sql = f"""
            SELECT COUNT(*),
                   COALESCE(SUM(pb.source_weight), 0),
                   COALESCE(SUM(pb.waste_weight),  0),
                   COALESCE(AVG(pya.real_yield),   0)
            FROM production_batches pb
            LEFT JOIN production_yield_analysis pya ON pya.batch_id = pb.id
            WHERE pb.estado = 'cerrado'
              AND DATE(pb.closed_at) = {date_expr}
        """
        r = db.execute(sql).fetchone()
        if r:
            vals["producciones_hoy"] = int(r[0] or 0)
            vals["kg_procesados"]    = float(r[1] or 0)
            vals["merma_dia"]        = float(r[2] or 0)
            vals["rendimiento"]      = float(r[3] or 0)
    except Exception:
        # Fallback: legacy producciones + produccion_detalle
        try:
            sql2 = f"""
                SELECT COUNT(*), COALESCE(SUM(cantidad_base), 0)
                FROM producciones
                WHERE estado = 'completada'
                  AND DATE(fecha) = {date_expr}
            """
            r2 = db.execute(sql2).fetchone()
            if r2:
                vals["producciones_hoy"] = int(r2[0] or 0)
                vals["kg_procesados"]    = float(r2[1] or 0)

            sql3 = f"""
                SELECT COALESCE(SUM(pd.cantidad_generada), 0)
                FROM produccion_detalle pd
                JOIN producciones p ON p.id = pd.produccion_id
                WHERE pd.tipo = 'merma'
                  AND DATE(p.fecha) = {date_expr}
            """
            r3 = db.execute(sql3).fetchone()
            if r3:
                vals["merma_dia"] = float(r3[0] or 0)

            kg = vals["kg_procesados"]
            merma = vals["merma_dia"]
            vals["rendimiento"] = round((1 - merma / kg) * 100, 1) if kg > 0 else 0.0
        except Exception:
            pass

    # Active lotes (applies to both schemas)
    try:
        row4 = _fetchall(db, "SELECT COUNT(*) FROM lotes WHERE estado='activo'")
        if row4:
            vals["lotes_activos"] = int(row4[0][0] or 0)
    except Exception:
        pass

    return vals


def get_active_lotes_count(db) -> int:
    """Return the number of active lotes."""
    try:
        rows = _fetchall(db, "SELECT COUNT(*) FROM lotes WHERE estado='activo'")
        return int(rows[0][0] or 0) if rows else 0
    except Exception:
        return 0


def get_recetas_list(db) -> List[Dict[str, Any]]:
    """
    Return active recipes for the recipe list UI table.

    Primary: product_recipes JOIN productos (with component count subquery).
    Fallback: legacy recetas table (when product_recipes is empty).

    Each row dict has keys: id, nombre, tipo_receta, producto_base, rendimiento, componentes.
    """
    product_expr = _product_recipes_product_expr(db)
    rows = []

    try:
        sql = f"""
            SELECT r.id,
                   COALESCE(r.nombre_receta, '') AS nombre,
                   COALESCE(r.tipo_receta, 'subproducto') AS tipo_receta,
                   COALESCE(p.nombre, '—') AS producto_base,
                   COALESCE(r.total_rendimiento, r.rendimiento_esperado_pct, 0) AS rendimiento,
                   (SELECT COUNT(*)
                    FROM product_recipe_components rc
                    WHERE rc.recipe_id = r.id) AS componentes
            FROM product_recipes r
            LEFT JOIN productos p ON p.id = {product_expr}
            WHERE COALESCE(r.is_active, 1) = 1
            ORDER BY r.nombre_receta LIMIT 300
        """
        raw = _fetchall(db, sql)
        rows = [
            {
                "id":           _col(r, 0, "id"),
                "nombre":       _col(r, 1, "nombre") or "",
                "tipo_receta":  _normalize_tipo_receta(_col(r, 2, "tipo_receta"), "subproducto"),
                "producto_base":_col(r, 3, "producto_base") or "—",
                "rendimiento":  float(_col(r, 4, "rendimiento") or 0),
                "componentes":  int(_col(r, 5, "componentes") or 0),
            }
            for r in raw
        ]
    except Exception as e:
        logger.warning("get_recetas_list product_recipes: %s", e)

    if not rows:
        try:
            sql_legacy = """
                SELECT r.id,
                       COALESCE(r.nombre, '') AS nombre,
                       COALESCE(r.tipo_receta, 'subproducto') AS tipo_receta,
                       COALESCE(p.nombre, '—') AS producto_base,
                       COALESCE(r.rendimiento_esperado_pct, 0) AS rendimiento,
                       0 AS componentes
                FROM recetas r
                LEFT JOIN productos p ON p.id = r.producto_base_id
                WHERE COALESCE(r.activo, 1) = 1
                ORDER BY r.nombre LIMIT 300
            """
            raw2 = _fetchall(db, sql_legacy)
            rows = [
                {
                    "id":           _col(r, 0, "id"),
                    "nombre":       _col(r, 1, "nombre") or "",
                    "tipo_receta":  _normalize_tipo_receta(_col(r, 2, "tipo_receta"), "subproducto"),
                    "producto_base":_col(r, 3, "producto_base") or "—",
                    "rendimiento":  float(_col(r, 4, "rendimiento") or 0),
                    "componentes":  int(_col(r, 5, "componentes") or 0),
                }
                for r in raw2
            ]
        except Exception as e2:
            logger.warning("get_recetas_list legacy: %s", e2)

    return rows


def get_recipe_components(db, recipe_id: int) -> List[Dict[str, Any]]:
    """
    Return component rows for a recipe.

    Each row dict has keys: nombre, cantidad, unidad, merma_pct, rendimiento_pct.
    """
    sql = """
        SELECT p.nombre,
               COALESCE(rc.cantidad, 0) AS cantidad,
               COALESCE(rc.unidad, p.unidad, 'kg') AS unidad,
               COALESCE(rc.merma_pct, 0) AS merma_pct,
               COALESCE(rc.rendimiento_pct, 0) AS rendimiento_pct
        FROM product_recipe_components rc
        LEFT JOIN productos p ON p.id = rc.component_product_id
        WHERE rc.recipe_id = ? ORDER BY rc.orden
    """
    raw = _fetchall(db, sql, (recipe_id,))
    return [
        {
            "nombre":          _col(r, 0, "nombre") or "",
            "cantidad":        float(_col(r, 1, "cantidad") or 0),
            "unidad":          _col(r, 2, "unidad") or "kg",
            "merma_pct":       float(_col(r, 3, "merma_pct") or 0),
            "rendimiento_pct": float(_col(r, 4, "rendimiento_pct") or 0),
        }
        for r in raw
    ]


def get_historial_carnica(db, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Return carnica reception history from recepciones_pollo.

    Each row dict has keys: fecha, producto, peso_bruto, merma, peso_neto.
    """
    sql = """
        SELECT COALESCE(fecha_produccion, created_at, '?') AS fecha,
               p.nombre AS producto,
               COALESCE(peso_bruto_kg, 0) AS peso_bruto,
               COALESCE(merma_kg, 0) AS merma,
               COALESCE(peso_neto_kg, peso_bruto_kg - merma_kg, 0) AS peso_neto
        FROM recepciones_pollo rp
        LEFT JOIN productos p ON p.id = rp.producto_id
        ORDER BY 1 DESC LIMIT ?
    """
    raw = _fetchall(db, sql, (limit,))
    return [
        {
            "fecha":      str(_col(r, 0, "fecha") or ""),
            "producto":   str(_col(r, 1, "producto") or ""),
            "peso_bruto": float(_col(r, 2, "peso_bruto") or 0),
            "merma":      float(_col(r, 3, "merma") or 0),
            "peso_neto":  float(_col(r, 4, "peso_neto") or 0),
        }
        for r in raw
    ]


def get_stock(db, product_id: int, sucursal_id: int) -> float:
    """
    Return current stock for a product at a branch.

    Delegates to InventoryBalanceQueryService — the canonical single source of
    truth that reads from inventario_actual (with fallback to productos.existencia).
    This ensures Producción and Inventario always see the same value.
    """
    try:
        from backend.application.queries.inventory_balance_service import (
            InventoryBalanceQueryService,
        )
        return InventoryBalanceQueryService(db).get_product_balance_float(
            int(product_id), int(sucursal_id)
        )
    except Exception as exc:
        logger.debug("get_stock: balance service unavailable: %s", exc)

    # Legacy fallback (should never be reached in normal operation)
    row = _fetchone(db,
        "SELECT COALESCE(cantidad, 0) FROM inventario_actual WHERE producto_id=? AND sucursal_id=?",
        (product_id, sucursal_id))
    if row is not None:
        return float(row[0] if not isinstance(row, dict) else row.get("COALESCE(cantidad, 0)", 0) or 0)
    row2 = _fetchone(db, "SELECT COALESCE(existencia, 0) FROM productos WHERE id=?", (product_id,))
    return float((row2[0] if row2 and not isinstance(row2, dict) else 0) or 0)


def get_stocks_for_products(
    db, product_ids: List[int], sucursal_id: int
) -> Dict[int, float]:
    """
    Return a {product_id: stock} dict for a list of product IDs.

    Uses get_stock() per product; callers should pass a deduplicated list.
    """
    return {pid: get_stock(db, pid, sucursal_id) for pid in product_ids}


def get_productos_activos(db) -> List[Dict[str, Any]]:
    """Return active products as {id, nombre} for UI dropdowns."""
    raw = _fetchall(db, "SELECT id, nombre FROM productos WHERE activo=1 ORDER BY nombre")
    return [
        {
            "id":     _col(r, 0, "id"),
            "nombre": str(_col(r, 1, "nombre") or ""),
        }
        for r in raw
    ]


def get_receta_by_product_id(db, product_id: int) -> Optional[Dict[str, Any]]:
    """
    Return {id, nombre_receta} for the first active recipe whose base product
    matches product_id.  Returns None when no recipe exists.

    Tries both product_id and base_product_id column names (schema auto-detect).
    """
    for col_name in ("product_id", "base_product_id"):
        sql = (
            f"SELECT id, COALESCE(nombre_receta, '') AS nombre_receta "
            f"FROM product_recipes "
            f"WHERE {col_name}=? AND COALESCE(is_active, 1)=1 "
            f"LIMIT 1"
        )
        try:
            row = _fetchone(db, sql, (product_id,))
            if row is not None:
                return {
                    "id":            _col(row, 0, "id"),
                    "nombre_receta": str(_col(row, 1, "nombre_receta") or ""),
                }
        except Exception:
            continue
    return None


def get_recetas_for_combo(db) -> List[Dict[str, Any]]:
    """
    Return recipes suitable for populating a QComboBox.

    Primary: product_recipes JOIN productos.
    Each row dict has keys: id, nombre, tipo_receta, producto_base_id,
    peso_promedio_kg, unidad_base, prod_nombre, prod_unidad.
    """
    product_expr = _product_recipes_product_expr(db)
    sql = f"""
        SELECT r.id,
               COALESCE(r.nombre_receta, '') AS nombre,
               COALESCE(r.tipo_receta, 'produccion') AS tipo_receta,
               {product_expr} AS producto_base_id,
               COALESCE(r.peso_promedio_kg, 1.0) AS peso_promedio_kg,
               COALESCE(r.unidad_base, p.unidad, 'kg') AS unidad_base,
               p.nombre AS prod_nombre,
               p.unidad  AS prod_unidad
        FROM product_recipes r
        LEFT JOIN productos p ON p.id = {product_expr}
        WHERE COALESCE(r.is_active, 1) = 1
        ORDER BY tipo_receta, nombre
    """
    raw = _fetchall(db, sql)
    return [
        {
            "id":               _col(r, 0, "id"),
            "nombre":           _col(r, 1, "nombre") or "",
            "tipo_receta":      _normalize_tipo_receta(_col(r, 2, "tipo_receta"), "produccion"),
            "producto_base_id": _col(r, 3, "producto_base_id"),
            "peso_promedio_kg": float(_col(r, 4, "peso_promedio_kg") or 1.0),
            "unidad_base":      _col(r, 5, "unidad_base") or "kg",
            "prod_nombre":      _col(r, 6, "prod_nombre") or "",
            "prod_unidad":      _col(r, 7, "prod_unidad") or "",
        }
        for r in raw
    ]


# ── Internal helper ───────────────────────────────────────────────────────────

def _col(row, index: int, key: str):
    """Extract a column by index (tuple rows) or by key (dict/Row rows)."""
    try:
        if isinstance(row, dict):
            return row.get(key)
        if hasattr(row, "keys"):
            return row[key]
        return row[index]
    except Exception:
        return None
