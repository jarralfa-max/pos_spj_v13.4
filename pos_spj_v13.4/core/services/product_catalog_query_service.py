from __future__ import annotations

from typing import Any, Dict, Set


def _scalar(db, query: str, params=()) -> int:
    row = db.execute(query, params).fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


def get_product_configuration_kpis(db) -> Dict[str, int]:
    """KPIs de configuración de catálogo (sin métricas de inventario)."""
    activos = _scalar(db, "SELECT COUNT(*) FROM productos WHERE COALESCE(activo,1)=1")
    sin_tipo = _scalar(
        db,
        "SELECT COUNT(*) FROM productos WHERE COALESCE(activo,1)=1 "
        "AND (tipo_producto IS NULL OR TRIM(tipo_producto)='')"
    )
    receta_pendiente = _scalar(
        db,
        "SELECT COUNT(*) FROM productos p "
        "WHERE COALESCE(p.activo,1)=1 "
        "AND LOWER(COALESCE(p.tipo_producto,'')) IN ('compuesto','procesable','producido') "
        "AND NOT EXISTS (SELECT 1 FROM product_recipes r WHERE r.base_product_id=p.id AND COALESCE(r.is_active,1)=1)"
    )
    sin_costo = _scalar(
        db,
        "SELECT COUNT(*) FROM productos WHERE COALESCE(activo,1)=1 "
        "AND COALESCE(precio_compra,0)<=0"
    )
    inactivos = _scalar(db, "SELECT COUNT(*) FROM productos WHERE COALESCE(activo,1)=0")
    return {
        "activos": activos,
        "sin_tipo": sin_tipo,
        "receta_pendiente": receta_pendiente,
        "sin_costo": sin_costo,
        "inactivos": inactivos,
    }


def get_catalog_filter_ids(db, filter_key: str) -> Set[int]:
    queries = {
        "sin_tipo": (
            "SELECT id FROM productos WHERE COALESCE(activo,1)=1 "
            "AND (tipo_producto IS NULL OR TRIM(tipo_producto)='')"
        ),
        "receta_pendiente": (
            "SELECT p.id FROM productos p "
            "WHERE COALESCE(p.activo,1)=1 "
            "AND LOWER(COALESCE(p.tipo_producto,'')) IN ('compuesto','procesable','producido') "
            "AND NOT EXISTS (SELECT 1 FROM product_recipes r WHERE r.base_product_id=p.id AND COALESCE(r.is_active,1)=1)"
        ),
        "sin_costo": (
            "SELECT id FROM productos WHERE COALESCE(activo,1)=1 "
            "AND COALESCE(precio_compra,0)<=0"
        ),
    }
    q = queries.get(filter_key)
    if not q:
        return set()
    rows = db.execute(q).fetchall()
    out: Set[int] = set()
    for r in rows:
        out.add(int((r["id"] if hasattr(r, "keys") else r[0]) or 0))
    return out
