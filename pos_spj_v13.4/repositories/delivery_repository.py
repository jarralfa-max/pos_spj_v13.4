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
            "fecha_actualizacion DATETIME",
            "historial_cambios TEXT",
        ):
            try:
                self.db.execute(f"ALTER TABLE delivery_orders ADD COLUMN {col}")
            except Exception:
                pass
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_delivery_estado ON delivery_orders(estado, fecha)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_delivery_wa ON delivery_orders(whatsapp_order_id)")
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
            "SELECT d.*, v.id as venta_relacionada "
            "FROM delivery_orders d "
            "LEFT JOIN ventas v ON v.id = d.venta_id "
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
                data["direccion"],
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
        self._insert_history(oid, None, "pendiente", data.get("usuario", "sistema"), "creación")
        self.db.commit()
        return oid

    def upsert_order_from_whatsapp(self, payload: Dict[str, Any], usuario: str = "whatsapp") -> int:
        wa_id = payload.get("whatsapp_order_id") or payload.get("order_id")
        row = None
        if wa_id:
            row = self.db.execute(
                "SELECT id FROM delivery_orders WHERE whatsapp_order_id=?", (str(wa_id),)
            ).fetchone()
        data = {
            "folio": payload.get("folio") or payload.get("codigo"),
            "whatsapp_order_id": str(wa_id) if wa_id else None,
            "cliente_nombre": payload.get("cliente") or payload.get("cliente_nombre"),
            "cliente_tel": payload.get("telefono") or payload.get("cliente_tel"),
            "direccion": payload.get("direccion") or "",
            "lat": payload.get("lat"),
            "lng": payload.get("lng"),
            "total": payload.get("total") or 0,
            "notas": payload.get("notas", ""),
            "usuario": usuario,
            "sucursal_id": payload.get("sucursal_id", 1),
        }
        if row:
            oid = int(row[0])
            self.db.execute(
                """
                UPDATE delivery_orders
                SET folio=COALESCE(?, folio), cliente_nombre=COALESCE(?,cliente_nombre),
                    cliente_tel=COALESCE(?,cliente_tel), direccion=COALESCE(?,direccion),
                    lat=COALESCE(?,lat), lng=COALESCE(?,lng), total=COALESCE(?,total),
                    notas=COALESCE(?,notas), fecha_actualizacion=datetime('now')
                WHERE id=?
                """,
                (
                    data["folio"], data["cliente_nombre"], data["cliente_tel"], data["direccion"],
                    data["lat"], data["lng"], data["total"], data["notas"], oid,
                ),
            )
        else:
            oid = self.create_order(data)
        self.db.commit()
        return oid

    def update_status(self, order_id: int, new_status: str, usuario: str, observacion: str = "", responsable: str = "") -> None:
        row = self.db.execute(
            "SELECT estado, historial_cambios FROM delivery_orders WHERE id=?", (order_id,)
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
