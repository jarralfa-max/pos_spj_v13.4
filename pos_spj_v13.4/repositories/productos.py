
# repositories/productos.py
# ── ProductRepository — Enterprise Repository Layer ──────────────────────────
from __future__ import annotations

import logging
import json
from datetime import datetime
from typing import Dict, List, Optional

from core.events.event_bus import get_bus as _get_bus
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.repositories.productos")

PRODUCTO_CREADO      = "PRODUCTO_CREADO"
PRODUCTO_ACTUALIZADO = "PRODUCTO_ACTUALIZADO"
PRODUCTO_ELIMINADO   = "PRODUCTO_ELIMINADO"

class ProductoDeletionError(Exception):
    pass

class ProductoNombreDuplicadoError(Exception):
    pass

class ProductoRepository:

    def __init__(self, db):
        self.db = db

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_all(self, *, include_inactive: bool = False, categoria: str = "",
                search: str = "") -> List[Dict]:
        conditions = []
        params: List = []
        if not include_inactive:
            conditions.append("p.is_active = 1")
        if categoria:
            conditions.append("p.categoria = ?")
            params.append(categoria)
        if search:
            conditions.append("(p.nombre LIKE ? OR p.categoria LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        
        # CORRECCIÓN: Uso de cursor para fetchall
        cursor = self.db.cursor()
        cursor.execute(f"""
            SELECT p.id, p.nombre, p.precio, p.existencia, p.stock_minimo,
                   p.unidad, p.categoria, p.oculto, p.es_compuesto,
                   p.es_subproducto, p.is_active, p.deleted_at,
                   p.imagen_path
            FROM productos p
            {where}
            ORDER BY p.nombre
        """, params)
        
        # Convertir filas a diccionarios para compatibilidad con la UI
        columnas = [col[0] for col in cursor.description]
        return [dict(zip(columnas, row)) for row in cursor.fetchall()]

    def get_by_id(self, producto_id: str) -> Optional[Dict]:
        # CORRECCIÓN: Uso de cursor para fetchone
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
        row = cursor.fetchone()
        if row:
            columnas = [col[0] for col in cursor.description]
            return dict(zip(columnas, row))
        return None

    def get_categories(self):
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT DISTINCT COALESCE(categoria,'') FROM productos "
            "WHERE COALESCE(oculto,0)=0 AND COALESCE(activo,1)=1 "
            "AND categoria IS NOT NULL AND categoria != '' "
            "ORDER BY categoria"
        )
        return [r[0] for r in cursor.fetchall() if r[0]]

    def get_by_barcode(self, codigo: str) -> Optional[Dict]:
        """Busca producto activo por código de barras, código interno o ID."""
        cursor = self.db.cursor()
        cursor.execute(
            """SELECT id, nombre, precio_venta, precio_kilo,
                      existencia, unidad, tipo, imagen_path,
                      categoria, descripcion,
                      COALESCE(codigo_barras,'') as codigo_barras
               FROM productos
               WHERE (COALESCE(codigo_barras,'')=? OR COALESCE(codigo,'')=? OR CAST(id AS TEXT)=?)
                 AND COALESCE(activo,1)=1 AND COALESCE(oculto,0)=0
               LIMIT 1""",
            (codigo, codigo, codigo),
        )
        row = cursor.fetchone()
        if row:
            cols = [c[0] for c in cursor.description]
            return dict(zip(cols, row))
        return None

    def get_for_sale(self, search: str = "") -> List[Dict]:
        params: List = []
        where_extra = ""
        if search:
            where_extra = "AND (p.nombre LIKE ? OR p.categoria LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
            
        cursor = self.db.cursor()
        cursor.execute(f"""
            SELECT p.id, p.nombre, p.precio, p.existencia,
                   p.unidad, p.categoria, p.imagen_path,
                   p.es_compuesto, p.es_subproducto
            FROM productos p
            WHERE p.is_active = 1 AND p.oculto = 0
            {where_extra}
            ORDER BY p.nombre
        """, params)
        
        columnas = [col[0] for col in cursor.description]
        return [dict(zip(columnas, row)) for row in cursor.fetchall()]

    # ── Búsqueda para el widget de escáner (Remediación F: SQL fuera de la UI) ──
    #  Preservan EXACTAMENTE las consultas y columnas que usaba ProductSearchWidget.

    def buscar_exacto_para_scanner(self, codigo: str) -> Optional[Dict]:
        """Coincidencia exacta por código de barras, código interno o ID."""
        row = self.db.execute(
            """SELECT id, nombre, COALESCE(codigo,'') as codigo,
                      COALESCE(codigo_barras,'') as codigo_barras,
                      precio, COALESCE(precio_compra,0) as precio_compra,
                      COALESCE(existencia,0) as existencia,
                      COALESCE(unidad,'pz') as unidad
               FROM productos
               WHERE (COALESCE(codigo_barras,'')=? OR codigo=? OR CAST(id AS TEXT)=?)
                 AND COALESCE(oculto,0)=0 AND COALESCE(activo,1)=1
               LIMIT 1""",
            (codigo, codigo, codigo),
        ).fetchone()
        return dict(row) if row else None

    def buscar_para_scanner(self, text: str) -> List[Dict]:
        """Búsqueda difusa por nombre/código/barcode/ID para el popup del escáner."""
        rows = self.db.execute(
            """SELECT id, nombre,
                      COALESCE(codigo,'') as codigo,
                      COALESCE(codigo_barras,'') as codigo_barras,
                      precio,
                      COALESCE(precio_compra,0) as precio_compra,
                      COALESCE(existencia,0) as existencia,
                      COALESCE(unidad,'pz') as unidad
               FROM productos
               WHERE (
                   nombre          LIKE ?
                OR COALESCE(codigo,'')      LIKE ?
                OR COALESCE(codigo_barras,'') LIKE ?
                OR CAST(id AS TEXT)          = ?
               )
               AND COALESCE(oculto,0)=0
               AND COALESCE(activo,1)=1
               ORDER BY
                 CASE WHEN COALESCE(codigo_barras,'')=? THEN 0
                      WHEN COALESCE(codigo,'')=?        THEN 1
                      WHEN CAST(id AS TEXT)=?           THEN 2
                      ELSE 3 END,
                 nombre
               LIMIT 20""",
            (f"%{text}%", f"%{text}%", f"%{text}%", text, text, text, text),
        ).fetchall()
        return [dict(r) for r in rows]

    def listar_para_etiquetas(self, limite: int = 2000) -> list:
        """Catálogo mínimo (id, nombre, precio, unidad) para el diseñador de etiquetas.
        Devuelve filas crudas; el widget arma su caché por índice."""
        return self.db.execute(
            "SELECT id, nombre, COALESCE(precio,0), COALESCE(unidad,'pz') "
            "FROM productos WHERE activo=1 ORDER BY nombre LIMIT ?",
            (int(limite),),
        ).fetchall()

    def check_name_available(self, nombre: str,
                              exclude_id: Optional[str] = None) -> bool:
        normalised = nombre.strip().lower()
        cursor = self.db.cursor()
        if exclude_id:
            cursor.execute("""
        SELECT id FROM productos
                WHERE nombre_normalizado = ? AND id != ? AND is_active = 1
            """, (normalised, exclude_id))
        else:
            cursor.execute("""
        SELECT id FROM productos
                WHERE nombre_normalizado = ? AND is_active = 1
            """, (normalised,))
        return cursor.fetchone() is None

    def has_sales(self, producto_id: str) -> bool:
        cursor = self.db.cursor()
        cursor.execute("SELECT COUNT(*) FROM detalles_venta WHERE producto_id = ?", (producto_id,))
        row = cursor.fetchone()
        return (row[0] if row else 0) > 0

    def has_movements(self, producto_id: str) -> bool:
        cursor = self.db.cursor()
        cursor.execute("SELECT COUNT(*) FROM movimientos_inventario WHERE producto_id = ?", (producto_id,))
        row = cursor.fetchone()
        return (row[0] if row else 0) > 0

    def has_recipes(self, producto_id: str) -> bool:
        cursor = self.db.cursor()
        cursor.execute("SELECT COUNT(*) FROM componentes_producto WHERE producto_componente_id = ?", (producto_id,))
        row = cursor.fetchone()
        if row and row[0] > 0:
            return True
        cursor.execute("SELECT COUNT(*) FROM componentes_producto WHERE producto_compuesto_id = ?", (producto_id,))
        row2 = cursor.fetchone()
        return (row2[0] if row2 else 0) > 0

    # ── Write ────────────────────────────────────────────────────────────────

    def create(self, data: Dict, usuario: str) -> str:
        nombre = data.get("nombre", "").strip()
        normalised = nombre.lower()

        # REGLA CERO: identidad UUIDv7 acuñada con new_uuid(), nunca rowid implícito.
        producto_id = data.get("id") or new_uuid()
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO productos (id, nombre, nombre_normalizado, precio, existencia, stock_minimo, unidad, categoria, oculto, es_compuesto, es_subproducto, producto_padre_id, imagen_path, is_active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
        (producto_id, nombre, normalised, data.get("precio", 0), data.get("existencia", 0), data.get("stock_minimo", 0), data.get("unidad", "kg"), data.get("categoria", ""), 1 if data.get("oculto") else 0, 1 if data.get("es_compuesto") else 0, 1 if data.get("es_subproducto") else 0, data.get("producto_padre_id"), data.get("imagen_path")))

        self.db.commit()

        self._write_audit("CREATE", str(producto_id), data, usuario)
        # POST-COMMIT: ruta canónica única (granular + products_changed + legacy).
        from core.events.catalog_events import publish_product_event
        publish_product_event(
            "created", product_id=str(producto_id), product_name=nombre,
            active=True, source_module="repositories.productos",
        )
        return producto_id

    def update(self, producto_id: str, data: Dict, usuario: str) -> None:
        nombre = data.get("nombre", "").strip()
        normalised = nombre.lower()
        
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE productos SET
                nombre = ?, nombre_normalizado = ?, precio = ?, existencia = ?,
                stock_minimo = ?, unidad = ?, categoria = ?, oculto = ?,
                es_compuesto = ?, es_subproducto = ?, producto_padre_id = ?,
                imagen_path = ?, fecha_actualizacion = ?
            WHERE id = ?
        """, (nombre, normalised, data.get("precio", 0), data.get("existencia", 0), data.get("stock_minimo", 0), data.get("unidad", "kg"), data.get("categoria", ""), 1 if data.get("oculto") else 0, 1 if data.get("es_compuesto") else 0, 1 if data.get("es_subproducto") else 0, data.get("producto_padre_id"), data.get("imagen_path"), self._now(), producto_id))
        
        self.db.commit()
        self._write_audit("UPDATE", str(producto_id), data, usuario)
        from core.events.catalog_events import publish_product_event
        publish_product_event(
            "updated", product_id=str(producto_id), product_name=nombre,
            active=True, source_module="repositories.productos",
        )

    def soft_delete(self, producto_id: str, usuario: str) -> None:
        cursor = self.db.cursor()
        cursor.execute("UPDATE productos SET is_active = 0, deleted_at = ?, oculto = 1 WHERE id = ?", (self._now(), producto_id))
        self.db.commit()
        from core.events.catalog_events import publish_product_event
        publish_product_event(
            "deactivated", product_id=str(producto_id), product_name="",
            active=False, source_module="repositories.productos",
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    def _write_audit(self, action: str, entity_id: str, data: Dict, usuario: str) -> None:
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO logs (id, modulo, accion, detalles, usuario)
                VALUES (?,?,?,?,?)
            """, (new_uuid(), "productos", f"PRODUCTO_{action}", json.dumps(data, default=str), usuario))
            self.db.commit()
        except Exception as exc:
            logger.warning("audit_log write failed: %s", exc)