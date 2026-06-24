"""Read-only repository for the compras (purchasing) UI: supplier/branch combos,
supplier info, recent purchases and CxP summary.

Extracted from modulos/compras_pro.py (Fase A). PyQt-free, headless-testable.
Reads only.
"""

from __future__ import annotations

import sqlite3
from typing import Any


class ComprasReadRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        try:
            if getattr(self._connection, "row_factory", None) is None:
                self._connection.row_factory = sqlite3.Row
        except Exception:
            pass

    def list_active_suppliers(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT id, nombre FROM proveedores WHERE activo=1 ORDER BY nombre"
        ).fetchall()
        return [{"id": r[0], "nombre": r[1]} for r in rows]

    def list_active_branches(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT id, nombre FROM sucursales WHERE activo=1 ORDER BY nombre"
        ).fetchall()
        return [{"id": r[0], "nombre": r[1]} for r in rows]

    def get_supplier(self, supplier_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM proveedores WHERE id=?", (supplier_id,)
        ).fetchone()
        return None if row is None else dict(row)

    def recent_purchases_for_supplier(
        self, supplier_id: str, branch_id: str, *, limit: int = 5
    ) -> list[tuple]:
        rows = self._connection.execute(
            "SELECT id, folio, fecha, total, estado FROM compras "
            "WHERE proveedor_id=? AND sucursal_id=? "
            "ORDER BY fecha DESC, id DESC LIMIT ?",
            (supplier_id, branch_id, int(limit)),
        ).fetchall()
        return [tuple(r) for r in rows]

    def get_config_value(self, key: str) -> str | None:
        """Read a config scalar from configuraciones(clave,valor) then settings(key,value)."""
        for tabla, col_k, col_v in (("configuraciones", "clave", "valor"),
                                    ("settings", "key", "value")):
            try:
                row = self._connection.execute(
                    f"SELECT {col_v} FROM {tabla} WHERE {col_k}=? LIMIT 1", (key,)
                ).fetchone()
                if row:
                    return row[0]
            except Exception:
                continue
        return None

    def get_avg_cost(self, product_id: str) -> float:
        row = self._connection.execute(
            "SELECT COALESCE(costo_promedio,0) FROM inventario_actual "
            "WHERE producto_id=? LIMIT 1", (product_id,)
        ).fetchone()
        return float(row[0]) if row and row[0] else 0.0

    def find_product_for_purchase(self, text: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT id, nombre, COALESCE(unidad,'pz') AS unidad, "
            "COALESCE(precio_compra, 0) AS costo "
            "FROM productos WHERE nombre LIKE ? OR codigo_interno=? OR barcode=? LIMIT 1",
            (f"%{text}%", text, text),
        ).fetchone()
        return None if row is None else dict(row)

    def list_purchase_templates(self, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT id, nombre FROM plantillas_compra ORDER BY nombre LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [{"id": r[0], "nombre": r[1]} for r in rows]

    def get_template_items(self, template_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT ti.producto_id, p.nombre, ti.cantidad, "
            "ti.costo_unitario, p.precio_compra "
            "FROM plantillas_compra_items ti "
            "JOIN productos p ON p.id = ti.producto_id "
            "WHERE ti.plantilla_id = ?",
            (template_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_supplier_name(self, supplier_id: str) -> str | None:
        row = self._connection.execute(
            "SELECT nombre FROM proveedores WHERE id=?", (supplier_id,)
        ).fetchone()
        return None if row is None else row[0]

    def get_purchase_for_reception(self, purchase_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT c.folio, c.total, c.proveedor_id, c.factura, "
            "COALESCE(p.nombre,'—') AS proveedor "
            "FROM compras c LEFT JOIN proveedores p ON p.id = c.proveedor_id "
            "WHERE c.id=? LIMIT 1",
            (purchase_id,),
        ).fetchone()
        return None if row is None else dict(row)

    def get_purchase_items_for_reception(self, purchase_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT dc.producto_id, COALESCE(pr.nombre, CAST(dc.producto_id AS TEXT)) AS nombre, "
            "COALESCE(pr.unidad,'pz') AS unidad, dc.cantidad, dc.precio_unitario "
            "FROM detalles_compra dc "
            "LEFT JOIN productos pr ON pr.id = dc.producto_id "
            "WHERE dc.compra_id=?",
            (purchase_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_purchase_requests(self, branch_id: str, *, limit: int = 40) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT id, folio, estado, proveedor_nombre, total, "
            "fecha_creacion, sucursal_id, usuario, notas "
            "FROM purchase_requests "
            "WHERE sucursal_id=? AND estado NOT IN ('CANCELADA','CONVERTIDA_A_PO') "
            "ORDER BY fecha_creacion DESC LIMIT ?",
            (branch_id, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_open_purchase_orders(self, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT id, folio, estado, proveedor_id, total, "
            "fecha_creacion, sucursal_id, usuario, notas "
            "FROM ordenes_compra "
            "WHERE estado IN ('ABIERTA','PARCIAL','borrador','pendiente') "
            "ORDER BY fecha_creacion DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    def products_with_recipe(self, product_ids: list) -> set:
        """Subset of product_ids that have an active recipe (base or output)."""
        if not product_ids:
            return set()
        ph = ",".join("?" * len(product_ids))
        rows = self._connection.execute(
            f"SELECT DISTINCT c FROM ("
            f" SELECT producto_id AS c FROM recetas "
            f" WHERE producto_id IN ({ph}) AND (activa=1 OR activo=1)"
            f" UNION "
            f" SELECT producto_base_id AS c FROM recetas "
            f" WHERE producto_base_id IN ({ph}) AND (activa=1 OR activo=1))",
            list(product_ids) + list(product_ids),
        ).fetchall()
        return {r[0] for r in rows}

    def cxp_pending_summary(self, supplier_id: str, branch_id: str) -> tuple:
        """(count, total) of pending/credit purchases for a supplier+branch."""
        row = self._connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(total), 0) FROM compras "
            "WHERE proveedor_id=? AND sucursal_id=? "
            "AND estado IN ('credito', 'pendiente')",
            (supplier_id, branch_id),
        ).fetchone()
        return (int(row[0] or 0), float(row[1] or 0)) if row else (0, 0.0)
