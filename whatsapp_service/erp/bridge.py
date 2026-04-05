# erp/bridge.py — Puente al ERP existente
"""
Wrapper que conecta con los use cases y servicios del ERP
sin modificar ningún archivo existente.

IMPORTANTE: Todo acceso al ERP pasa por aquí.
No se importa nada del ERP directamente en los flows.
"""
from __future__ import annotations
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger("wa.erp")


class ERPBridge:
    """Puente al ERP — acceso read/write a la BD y servicios."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def db(self) -> sqlite3.Connection:
        if not self._conn:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    # ── Sucursales ────────────────────────────────────────────────────────────

    def get_sucursales(self) -> List[Dict]:
        rows = self.db.execute(
            "SELECT id, nombre, COALESCE(direccion,'') as direccion "
            "FROM sucursales WHERE activa=1 ORDER BY nombre"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_sucursal(self, sucursal_id: int) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT id, nombre FROM sucursales WHERE id=? AND activa=1",
            (sucursal_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Clientes ──────────────────────────────────────────────────────────────

    def find_cliente_by_phone(self, phone: str) -> Optional[Dict]:
        phone_clean = phone[-10:] if len(phone) > 10 else phone

        row = self.db.execute("""
            SELECT *
            FROM clientes
            WHERE telefono LIKE ? AND activo=1
            LIMIT 1
        """, (f"%{phone_clean}",)).fetchone()

        if not row:
            return None

        cliente = dict(row)

        # Normalización para el bot
        cliente["credito_disponible"] = (
            cliente.get("credit_limit", 0) - cliente.get("credit_balance", 0)
        )

        return cliente

    def create_cliente_minimo(self, nombre: str, telefono: str) -> int:
        """Crea un cliente con datos mínimos (registro rápido por WA)."""
        cursor = self.db.execute(
            "INSERT INTO clientes (nombre, telefono, activo) VALUES (?, ?, 1)",
            (nombre, telefono))
        self.db.commit()
        return cursor.lastrowid

    def get_credito_disponible(self, cliente_id: int) -> float:
        row = self.db.execute("""
            SELECT COALESCE(credit_limit,0) - COALESCE(credit_balance,0)
            FROM clientes WHERE id=?
        """, (cliente_id,)).fetchone()

        return float(row[0]) if row else 0.0

    # ── Productos ─────────────────────────────────────────────────────────────

    def get_productos_by_category(self, categoria: str,
                                  sucursal_id: int) -> List[Dict]:
        rows = self.db.execute("""
            SELECT p.id, p.nombre, p.precio,
                   COALESCE(bi.quantity, p.existencia, 0) as stock,
                   COALESCE(p.unidad, 'kg') as unidad, p.categoria
            FROM productos p
            LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=?
            WHERE p.activo=1 AND COALESCE(p.oculto,0)=0
              AND LOWER(p.categoria) = LOWER(?)
            ORDER BY p.nombre
        """, (sucursal_id, categoria)).fetchall()
        return [dict(r) for r in rows]

    def get_categorias(self, sucursal_id: int) -> List[str]:
        rows = self.db.execute("""
            SELECT DISTINCT p.categoria
            FROM productos p
            WHERE p.activo=1 AND COALESCE(p.oculto,0)=0
              AND p.categoria IS NOT NULL AND p.categoria != ''
            ORDER BY p.categoria
        """).fetchall()
        return [r[0] for r in rows]

    def get_producto(self, producto_id: int,
                     sucursal_id: int) -> Optional[Dict]:
        row = self.db.execute("""
            SELECT p.id, p.nombre, p.precio,
                   COALESCE(bi.quantity, p.existencia, 0) as stock,
                   COALESCE(p.unidad, 'kg') as unidad, p.categoria
            FROM productos p
            LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=?
            WHERE p.id=?
        """, (sucursal_id, producto_id)).fetchone()
        return dict(row) if row else None

    # ── Ventas / Pedidos ──────────────────────────────────────────────────────

    def crear_pedido_wa(self, items: List[Dict], cliente_id: int,
                        sucursal_id: int, tipo_entrega: str,
                        direccion: str = "", fecha_entrega: str = "",
                        notas: str = "") -> Dict:
        """
        Crea un pedido desde WhatsApp.
        Inserta en la tabla ventas con estado 'pendiente_wa'.
        """
        import uuid
        folio = f"WA-{uuid.uuid4().hex[:8].upper()}"
        total = sum(it["cantidad"] * it["precio_unitario"] for it in items)

        cursor = self.db.execute("""
            INSERT INTO ventas (folio, cliente_id, total, estado,
                               sucursal_id, tipo_entrega, direccion_entrega,
                               fecha_entrega_programada, notas, canal, fecha)
            VALUES (?, ?, ?, 'pendiente_wa', ?, ?, ?, ?, ?, 'whatsapp',
                    datetime('now'))
        """, (folio, cliente_id, total, sucursal_id, tipo_entrega,
              direccion, fecha_entrega, notas))
        venta_id = cursor.lastrowid

        for it in items:
            self.db.execute("""
                INSERT INTO detalle_ventas (venta_id, producto_id, nombre,
                    cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (venta_id, it["producto_id"], it["nombre"],
                  it["cantidad"], it["precio_unitario"],
                  it["cantidad"] * it["precio_unitario"]))

        self.db.commit()
        return {"venta_id": venta_id, "folio": folio, "total": total}

    def get_ultimo_pedido(self, cliente_id: int) -> Optional[Dict]:
        """Obtiene el último pedido del cliente para "repetir"."""
        row = self.db.execute("""
            SELECT v.id, v.folio, v.total, v.fecha
            FROM ventas v
            WHERE v.cliente_id = ? AND v.estado NOT IN ('cancelada')
            ORDER BY v.fecha DESC LIMIT 1
        """, (cliente_id,)).fetchone()
        if not row:
            return None

        items = self.db.execute("""
            SELECT producto_id, nombre, cantidad,
                   precio_unitario, COALESCE(unidad, 'kg') as unidad
            FROM detalle_ventas WHERE venta_id=?
        """, (row["id"],)).fetchall()

        return {
            "venta_id": row["id"], "folio": row["folio"],
            "total": float(row["total"]), "fecha": row["fecha"],
            "items": [dict(i) for i in items],
        }

    def get_estado_pedido(self, folio: str) -> Optional[Dict]:
        row = self.db.execute(
            "SELECT folio, estado, total, fecha FROM ventas WHERE folio=?",
            (folio,)
        ).fetchone()
        return dict(row) if row else None

    # ── Cotizaciones ──────────────────────────────────────────────────────────

    def crear_cotizacion_wa(self, items: List[Dict], cliente_id: int,
                            sucursal_id: int, usuario: str = "whatsapp") -> Dict:
        import uuid
        folio = f"CWA-{uuid.uuid4().hex[:6].upper()}"
        total = sum(it["cantidad"] * it["precio_unitario"] for it in items)

        cursor = self.db.execute("""
            INSERT INTO cotizaciones (folio, cliente_id, cliente_nombre, total,
                                     estado, usuario, sucursal_id, fecha)
            VALUES (?, ?, (SELECT nombre FROM clientes WHERE id=?),
                    ?, 'pendiente', ?, ?, datetime('now'))
        """, (folio, cliente_id, cliente_id, total, usuario, sucursal_id))
        cot_id = cursor.lastrowid

        for it in items:
            self.db.execute("""
                INSERT INTO cotizaciones_detalle (cotizacion_id, producto_id,
                    nombre, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (cot_id, it["producto_id"], it["nombre"],
                  it["cantidad"], it["precio_unitario"],
                  it["cantidad"] * it["precio_unitario"]))

        self.db.commit()
        return {"cotizacion_id": cot_id, "folio": folio, "total": total}

    # ── Anticipos ─────────────────────────────────────────────────────────────

    def requiere_anticipo(self, cliente_id: int, total: float,
                          programado: bool = False) -> bool:
        """Determina si el pedido requiere anticipo."""
        credito = self.get_credito_disponible(cliente_id)
        # Requiere anticipo si:
        if credito < total:
            return True    # Sin crédito suficiente
        if programado:
            return True    # Pedido programado siempre requiere anticipo
        return False

    def registrar_anticipo(self, venta_id: int, monto: float,
                           metodo: str = "mercadopago") -> int:
        cursor = self.db.execute("""
            INSERT INTO anticipos (venta_id, monto, metodo, estado, fecha)
            VALUES (?, ?, ?, 'pendiente', datetime('now'))
        """, (venta_id, monto, metodo))
        self.db.commit()
        return cursor.lastrowid

    # ── Staff / RRHH ──────────────────────────────────────────────────────────

    def get_staff_phones(self, sucursal_id: int,
                         rol: str = "") -> List[str]:
        """Obtiene teléfonos del staff de una sucursal."""
        q = ("SELECT telefono FROM empleados "
             "WHERE sucursal_id=? AND activo=1 AND telefono IS NOT NULL")
        params = [sucursal_id]
        if rol:
            q += " AND rol=?"
            params.append(rol)
        rows = self.db.execute(q, params).fetchall()
        return [r[0] for r in rows if r[0]]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
