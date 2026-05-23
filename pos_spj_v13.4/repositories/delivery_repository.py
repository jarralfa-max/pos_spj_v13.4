from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spj.repositories.delivery")


class DeliveryRepository:
    """Capa de acceso a datos para delivery_orders y su trazabilidad."""

    def __init__(self, db):
        self.db = db
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER,
                folio TEXT,
                whatsapp_order_id TEXT,
                cliente_id INTEGER,
                cliente_nombre TEXT,
                cliente_tel TEXT,
                direccion TEXT NOT NULL,
                lat REAL,
                lng REAL,
                estado TEXT DEFAULT 'pendiente',
                notas TEXT,
                total REAL DEFAULT 0,
                responsable_entrega TEXT,
                usuario TEXT,
                fecha DATETIME DEFAULT (datetime('now')),
                fecha_actualizacion DATETIME,
                historial_cambios TEXT,
                driver_id INTEGER,
                sucursal_id INTEGER DEFAULT 1
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                delivery_id INTEGER NOT NULL,
                producto_id INTEGER,
                nombre TEXT NOT NULL,
                cantidad REAL NOT NULL DEFAULT 0,
                precio_unitario REAL NOT NULL DEFAULT 0,
                subtotal REAL NOT NULL DEFAULT 0,
                unidad TEXT DEFAULT 'kg',
                requested_qty REAL,
                prepared_qty REAL,
                final_qty REAL,
                prepared_by TEXT,
                prepared_at DATETIME,
                adjustment_reason TEXT,
                tolerance_exceeded INTEGER DEFAULT 0
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_order_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                estado_anterior TEXT,
                estado_nuevo TEXT,
                usuario TEXT,
                fecha DATETIME DEFAULT (datetime('now')),
                observacion TEXT
            )
            """
        )
        for col in (
            "folio TEXT",
            "whatsapp_order_id TEXT",
            "lat REAL",
            "lng REAL",
            "responsable_entrega TEXT",
            "usuario TEXT",
            "fecha DATETIME DEFAULT CURRENT_TIMESTAMP",
            "fecha_actualizacion DATETIME",
            "historial_cambios TEXT",
            "driver_id INTEGER",
            "sucursal_id INTEGER DEFAULT 1",
        ):
            try:
                self.db.execute(f"ALTER TABLE delivery_orders ADD COLUMN {col}")
            except Exception:
                pass
        for col in (
            "producto_id INTEGER",
            "unidad TEXT DEFAULT 'kg'",
            "requested_qty REAL",
            "prepared_qty REAL",
            "final_qty REAL",
            "prepared_by TEXT",
            "prepared_at DATETIME",
            "adjustment_reason TEXT",
            "tolerance_exceeded INTEGER DEFAULT 0",
        ):
            try:
                self.db.execute(f"ALTER TABLE delivery_items ADD COLUMN {col}")
            except Exception:
                pass
        # Ensure drivers table exists so LEFT JOIN always has a valid target
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS drivers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                vehiculo TEXT,
                activo INTEGER DEFAULT 1,
                en_ruta INTEGER DEFAULT 0,
                sucursal_id INTEGER DEFAULT 1,
                usuario_id INTEGER
            )
            """
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_delivery_estado ON delivery_orders(estado, fecha)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_delivery_wa ON delivery_orders(whatsapp_order_id)")
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_venta ON delivery_orders(venta_id) WHERE venta_id IS NOT NULL")
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_wa_order ON delivery_orders(whatsapp_order_id) WHERE whatsapp_order_id IS NOT NULL")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_delivery_items_delivery_id ON delivery_items(delivery_id)")
        try:
            self.db.commit()
        except Exception:
            pass

    @staticmethod
    def _normalize_status(status: str) -> str:
        mapping = {
            "asignado": "preparacion",
            "listo": "preparacion",
            "en_camino": "en_ruta",
        }
        return mapping.get((status or "").strip().lower(), (status or "pendiente").strip().lower())

    def list_orders(self, estado: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        sql = (
            "SELECT d.*, v.id as venta_relacionada, dr.nombre AS driver_nombre "
            "FROM delivery_orders d "
            "LEFT JOIN ventas v ON v.id = d.venta_id "
            "LEFT JOIN drivers dr ON dr.id = d.driver_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if estado and estado != "Todos":
            sql += " AND lower(d.estado) = ?"
            params.append(self._normalize_status(estado))
        sql += " ORDER BY COALESCE(d.fecha_actualizacion,d.fecha) DESC LIMIT ?"
        params.append(limit)

        rows = self.db.execute(sql, tuple(params)).fetchall()
        result: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            item["estado"] = self._normalize_status(item.get("estado"))
            item["venta_validada"] = bool(item.get("venta_relacionada") or not item.get("venta_id"))
            result.append(item)
        return result

    def create_order(self, data: Dict[str, Any]) -> int:
        hist = [{"estado": "pendiente", "usuario": data.get("usuario", "sistema")}]
        cur = self.db.execute(
            """
            INSERT INTO delivery_orders(
                venta_id, folio, whatsapp_order_id, cliente_id, cliente_nombre, cliente_tel,
                direccion, lat, lng, estado, notas, total, usuario, historial_cambios,
                sucursal_id
            ) VALUES(?,?,?,?,?,?,?,?,?,'pendiente',?,?,?,?,?)
            """,
            (
                data.get("venta_id"),
                data.get("folio"),
                data.get("whatsapp_order_id"),
                data.get("cliente_id"),
                data.get("cliente_nombre"),
                data.get("cliente_tel"),
                data.get("direccion") or "Sin dirección",
                data.get("lat"),
                data.get("lng"),
                data.get("notas", ""),
                float(data.get("total", 0) or 0),
                data.get("usuario", "sistema"),
                json.dumps(hist, ensure_ascii=False),
                int(data.get("sucursal_id", 1)),
            ),
        )
        oid = int(cur.lastrowid)
        self._replace_items(oid, data.get("items") or [])
        self._insert_history(oid, None, "pendiente", data.get("usuario", "sistema"), "creación")
        self.db.commit()
        return oid

    def upsert_order_from_whatsapp(self, payload: Dict[str, Any], usuario: str = "whatsapp") -> int:
        wa_id = payload.get("whatsapp_order_id") or payload.get("order_id")
        venta_id = payload.get("venta_id") or payload.get("id")
        row = None
        if wa_id:
            row = self.db.execute(
                "SELECT id FROM delivery_orders WHERE whatsapp_order_id=?", (str(wa_id),)
            ).fetchone()
        if not row and venta_id:
            row = self.db.execute(
                "SELECT id FROM delivery_orders WHERE venta_id=?", (int(venta_id),)
            ).fetchone()

        data = {
            "venta_id": int(venta_id) if venta_id else None,
            "folio": payload.get("folio") or payload.get("codigo"),
            "whatsapp_order_id": str(wa_id or f"venta:{venta_id}"),
            "cliente_id": payload.get("cliente_id"),
            "cliente_nombre": payload.get("cliente") or payload.get("cliente_nombre"),
            "cliente_tel": payload.get("telefono") or payload.get("cliente_tel") or payload.get("cliente_telefono"),
            "direccion": payload.get("direccion") or payload.get("direccion_entrega") or "Sin dirección",
            "lat": payload.get("lat"),
            "lng": payload.get("lng"),
            "total": payload.get("total") or 0,
            "notas": payload.get("notas", ""),
            "usuario": usuario,
            "sucursal_id": payload.get("sucursal_id", 1),
            "items": payload.get("items") or [],
        }
        if row:
            oid = int(row[0])
            self.db.execute(
                """
                UPDATE delivery_orders
                SET venta_id=COALESCE(?, venta_id),
                    folio=COALESCE(?, folio),
                    whatsapp_order_id=COALESCE(?, whatsapp_order_id),
                    cliente_id=COALESCE(?, cliente_id),
                    cliente_nombre=COALESCE(NULLIF(?,''), cliente_nombre),
                    cliente_tel=COALESCE(NULLIF(?,''), cliente_tel),
                    direccion=COALESCE(NULLIF(?,''), direccion),
                    lat=COALESCE(?,lat), lng=COALESCE(?,lng), total=COALESCE(?,total),
                    notas=COALESCE(NULLIF(?,''),notas), fecha_actualizacion=datetime('now')
                WHERE id=?
                """,
                (
                    data["venta_id"], data["folio"], data["whatsapp_order_id"], data["cliente_id"],
                    data["cliente_nombre"], data["cliente_tel"], data["direccion"],
                    data["lat"], data["lng"], data["total"], data["notas"], oid,
                ),
            )
            if data["items"]:
                self._replace_items(oid, data["items"])
        else:
            oid = self.create_order(data)
        self.db.commit()
        return oid

    def _replace_items(self, order_id: int, items: List[Dict[str, Any]]) -> None:
        """Sincroniza delivery_items desde el payload WA sin duplicar líneas."""
        try:
            self.db.execute("DELETE FROM delivery_items WHERE delivery_id=?", (order_id,))
            for it in items:
                qty = float(it.get("cantidad") or it.get("qty") or 0)
                price = float(it.get("precio_unitario") or it.get("precio") or it.get("unit_price") or 0)
                subtotal = float(it.get("subtotal") or (qty * price))
                self.db.execute(
                    """
                    INSERT INTO delivery_items(
                        delivery_id, producto_id, nombre, cantidad,
                        precio_unitario, subtotal, unidad, requested_qty
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        order_id,
                        it.get("producto_id"),
                        it.get("nombre") or it.get("name") or "Producto",
                        qty,
                        price,
                        subtotal,
                        it.get("unidad") or "kg",
                        qty,
                    ),
                )
        except Exception as exc:
            logger.warning("_replace_items delivery_id=%s falló: %s", order_id, exc)

    def update_status(self, order_id: int, new_status: str, usuario: str, observacion: str = "", responsable: str = "") -> None:
        row = self.db.execute(
            "SELECT estado, historial_cambios, venta_id FROM delivery_orders WHERE id=?", (order_id,)
        ).fetchone()
        if not row:
            raise ValueError("Pedido no encontrado")
        prev = self._normalize_status(row[0])
        new_status = self._normalize_status(new_status)
        hist = []
        if row[1]:
            try:
                hist = json.loads(row[1])
            except Exception:
                hist = []
        hist.append({"estado": new_status, "usuario": usuario})
        self.db.execute(
            """
            UPDATE delivery_orders
            SET estado=?, responsable_entrega=COALESCE(?, responsable_entrega),
                usuario=?, fecha_actualizacion=datetime('now'), historial_cambios=?
            WHERE id=?
            """,
            (new_status, responsable or None, usuario, json.dumps(hist, ensure_ascii=False), order_id),
        )
        venta_id = row[2]
        if venta_id:
            venta_estado = {
                "pendiente": "pendiente_wa",
                "preparacion": "en_preparacion",
                "en_ruta": "en_ruta",
                "entregado": "entregada",
                "cancelado": "cancelada",
            }.get(new_status)
            if venta_estado:
                try:
                    self.db.execute("UPDATE ventas SET estado=? WHERE id=?", (venta_estado, venta_id))
                except Exception as exc:
                    logger.debug("No se pudo sincronizar estado venta=%s: %s", venta_id, exc)
        self._insert_history(order_id, prev, new_status, usuario, observacion)
        self.db.commit()

    def _insert_history(self, order_id: int, old: Optional[str], new: str, usuario: str, obs: str) -> None:
        self.db.execute(
            """
            INSERT INTO delivery_order_history(order_id, estado_anterior, estado_nuevo, usuario, observacion)
            VALUES(?,?,?,?,?)
            """,
            (order_id, old, new, usuario, obs),
        )

    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute("SELECT * FROM delivery_orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None