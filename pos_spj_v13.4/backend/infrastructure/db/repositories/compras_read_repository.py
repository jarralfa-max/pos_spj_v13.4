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
        """Sucursales activas con identidad UUID válida (la columna es `activa`,
        no `activo` — el nombre equivocado hacía fallar el combo de Compras y
        lo mandaba al fallback 'Sucursal Principal')."""
        rows = self._connection.execute(
            "SELECT id, nombre FROM sucursales "
            "WHERE activa=1 "
            "  AND id IS NOT NULL AND TRIM(id) != '' "
            "  AND LOWER(TRIM(id)) NOT IN ('none','null') "
            "ORDER BY nombre"
        ).fetchall()
        return [{"id": str(r[0]), "nombre": r[1]} for r in rows]

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

    def get_purchase_folio(self, purchase_id: str) -> str | None:
        row = self._connection.execute(
            "SELECT folio FROM compras WHERE id=? LIMIT 1", (purchase_id,)
        ).fetchone()
        return None if row is None else row[0]

    def get_purchase_id_by_folio(self, folio: str) -> Any | None:
        row = self._connection.execute(
            "SELECT id FROM compras WHERE folio=? LIMIT 1", (folio,)
        ).fetchone()
        return None if row is None else row[0]

    def get_supervisor_pin(self) -> str:
        """Supervisor PIN from configuracion / settings / parametros (first hit)."""
        for tabla, col_k, col_v in (("configuracion", "clave", "valor"),
                                    ("settings", "key", "value"),
                                    ("parametros", "parametro", "valor")):
            try:
                row = self._connection.execute(
                    f"SELECT {col_v} FROM {tabla} WHERE {col_k}=? LIMIT 1",
                    ("pin_supervisor",),
                ).fetchone()
                if row:
                    return str(row[0] or "").strip()
            except Exception:
                continue
        return ""

    def list_purchase_history(self, branch_id: str, desde: str, hasta: str, *, limit: int = 200) -> list[tuple]:
        rows = self._connection.execute(
            "SELECT c.folio, c.fecha, COALESCE(p.nombre,'(sin proveedor)') as proveedor, "
            "c.usuario, c.total, c.estado, c.id, "
            "COALESCE(c.condicion_pago,'liquidado') AS condicion_pago, "
            "COALESCE(c.moneda,'MXN') AS moneda, "
            "COALESCE(c.purchase_order_id, 0) AS po_id, "
            "COALESCE(oc.estado, '') AS po_estado "
            "FROM compras c "
            "LEFT JOIN proveedores p ON p.id=c.proveedor_id "
            "LEFT JOIN ordenes_compra oc ON oc.id=c.purchase_order_id "
            "WHERE c.sucursal_id=? AND c.fecha BETWEEN ? AND ? "
            "ORDER BY c.fecha DESC LIMIT ?",
            (branch_id, desde, hasta, int(limit)),
        ).fetchall()
        return [tuple(r) for r in rows]

    def get_recipe_components(self, product_id: str) -> list[dict[str, Any]]:
        """Recipe components from receta_componentes (m000 schema)."""
        rows = self._connection.execute(
            "SELECT rc.producto_id AS insumo_id, "
            "COALESCE(rc.cantidad, 0) AS cantidad_insumo, p.nombre AS insumo_nombre "
            "FROM receta_componentes rc "
            "JOIN recetas r ON r.id = rc.receta_id "
            "JOIN productos p ON p.id = rc.producto_id "
            "WHERE (r.producto_base_id=? OR r.producto_id=?) AND (r.activo=1 OR r.activa=1)",
            (product_id, product_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recipe_components_v2(self, product_id: str) -> list[dict[str, Any]]:
        """Fallback recipe components from product_recipe_components."""
        rows = self._connection.execute(
            "SELECT rc.component_product_id AS insumo_id, "
            "COALESCE(rc.cantidad, 0) AS cantidad_insumo, p.nombre AS insumo_nombre "
            "FROM product_recipe_components rc "
            "JOIN product_recipes r ON r.id = rc.recipe_id "
            "JOIN productos p ON p.id = rc.component_product_id "
            "WHERE r.base_product_id=? AND r.is_active=1",
            (product_id,),
        ).fetchall()
        return [dict(r) for r in rows]

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

    def list_containers_brief(self, *, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT id, codigo, tipo FROM contenedores "
            f"ORDER BY fecha_creado DESC LIMIT {int(limit)}"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_products_brief(self, *, limit: int = 2000) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT id, nombre, codigo_barras FROM productos "
            f"ORDER BY nombre LIMIT {int(limit)}"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_pending_containers(self, *, filter_text: str = "", limit: int = 200) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, codigo, tipo, fecha_creado, COALESCE(descripcion,'') AS desc "
            "FROM contenedores WHERE estado='generado'"
        )
        params: list = []
        if filter_text:
            sql += " AND (codigo LIKE ? OR descripcion LIKE ?)"
            params += [f"%{filter_text}%"] * 2
        sql += f" ORDER BY fecha_creado DESC LIMIT {int(limit)}"
        return [dict(r) for r in self._connection.execute(sql, params).fetchall()]

    def list_container_history(
        self, *, filter_text: str = "", date_from: str = "",
        date_to: str = "", supplier_id: str = "", limit: int = 500,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT c.codigo, c.tipo, "
            "COALESCE(p.nombre,'(sin asignar)') AS proveedor, "
            "COALESCE(c.folio_factura,'—') AS factura, "
            "COALESCE(c.fecha_factura,'—') AS fecha_compra, "
            "COALESCE(s.nombre,'—') AS destino, c.estado, c.total, "
            "COALESCE(c.fecha_recibido,'—') AS fecha_recibido "
            "FROM contenedores c "
            "LEFT JOIN proveedores p ON p.id = c.proveedor_id "
            "LEFT JOIN sucursales s ON s.id = c.sucursal_destino WHERE 1=1"
        )
        params: list = []
        if filter_text:
            sql += " AND (c.codigo LIKE ? OR p.nombre LIKE ? OR c.folio_factura LIKE ?)"
            params += [f"%{filter_text}%"] * 3
        if date_from:
            sql += " AND c.fecha_creado >= ?"; params.append(date_from)
        if date_to:
            sql += " AND c.fecha_creado <= ?"; params.append(date_to + " 23:59:59")
        if supplier_id:
            sql += " AND c.proveedor_id=?"; params.append(supplier_id)
        sql += f" ORDER BY c.fecha_creado DESC LIMIT {int(limit)}"
        return [dict(r) for r in self._connection.execute(sql, params).fetchall()]

    def get_container_history_detail(self, codigo: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT c.codigo, c.tipo, c.estado, c.total, "
            "COALESCE(p.nombre,'—') AS proveedor, "
            "COALESCE(c.folio_factura,'—') AS factura, "
            "COALESCE(s.nombre,'—') AS destino, "
            "c.fecha_creado, c.fecha_asignado, c.fecha_recibido "
            "FROM contenedores c "
            "LEFT JOIN proveedores p ON p.id = c.proveedor_id "
            "LEFT JOIN sucursales s ON s.id = c.sucursal_destino "
            "WHERE c.codigo=? LIMIT 1",
            (codigo,),
        ).fetchone()
        return None if row is None else dict(row)

    def _reception_list(self, base: str, filter_cols: str, filter_text: str,
                        order: str, limit: int) -> list[dict[str, Any]]:
        sql = base
        params: list = []
        if filter_text:
            sql += f" AND ({filter_cols})"
            params += [f"%{filter_text}%"] * 2
        sql += f" {order} LIMIT {int(limit)}"
        return [dict(r) for r in self._connection.execute(sql, params).fetchall()]

    def list_pos_for_reception(self, *, filter_text: str = "", limit: int = 100) -> list[dict[str, Any]]:
        return self._reception_list(
            "SELECT oc.id, oc.folio, COALESCE(p.nombre,'—') AS proveedor, "
            "COALESCE(oc.total,0) AS total "
            "FROM ordenes_compra oc LEFT JOIN proveedores p ON p.id=oc.proveedor_id "
            "WHERE oc.estado='PARA_RECEPCION'",
            "oc.folio LIKE ? OR p.nombre LIKE ?", filter_text,
            "ORDER BY oc.fecha_actualizacion DESC", limit,
        )

    def list_purchases_for_reception(self, *, filter_text: str = "", limit: int = 100) -> list[dict[str, Any]]:
        return self._reception_list(
            "SELECT c.id, c.folio, COALESCE(p.nombre,'—') AS proveedor, "
            "COALESCE(c.total,0) AS total "
            "FROM compras c LEFT JOIN proveedores p ON p.id=c.proveedor_id "
            "WHERE c.estado='para_recepcion'",
            "c.folio LIKE ? OR p.nombre LIKE ?", filter_text,
            "ORDER BY c.fecha DESC", limit,
        )

    def list_assigned_containers_for_reception(self, *, filter_text: str = "", limit: int = 200) -> list[dict[str, Any]]:
        return self._reception_list(
            "SELECT c.id, c.codigo, c.tipo, COALESCE(p.nombre,'—') AS proveedor, "
            "COALESCE(c.total,0) AS total, c.estado "
            "FROM contenedores c LEFT JOIN proveedores p ON p.id=c.proveedor_id "
            "WHERE c.estado IN ('asignado','en_recepcion','recepcion_parcial')",
            "c.codigo LIKE ? OR p.nombre LIKE ?", filter_text,
            "ORDER BY c.fecha_asignado DESC", limit,
        )

    def cxp_pending_summary(self, supplier_id: str, branch_id: str) -> tuple:
        """(count, total) of pending/credit purchases for a supplier+branch."""
        row = self._connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(total), 0) FROM compras "
            "WHERE proveedor_id=? AND sucursal_id=? "
            "AND estado IN ('credito', 'pendiente')",
            (supplier_id, branch_id),
        ).fetchone()
        return (int(row[0] or 0), float(row[1] or 0)) if row else (0, 0.0)
