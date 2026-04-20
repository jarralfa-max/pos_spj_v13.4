
# core/services/inventory/unified_inventory_service.py — SPJ POS v7
from __future__ import annotations
import logging, uuid
from typing import List
from core.db.connection import get_connection, transaction
logger = logging.getLogger("spj.inventory")
MOVEMENT_TYPES = frozenset({"purchase","sale","adjustment","waste","production","return","transfer"})
class InventoryError(Exception): pass
class StockInsuficienteError(InventoryError):
    def __init__(self, producto, disponible, requerido):
        super().__init__(f"Stock insuficiente: {producto}")
        self.producto=producto; self.disponible=disponible; self.requerido=requerido
class UnifiedInventoryService:
    def __init__(self, conn=None, sucursal_id=1, usuario="Sistema"):
        self.conn=conn or get_connection(); self.sucursal_id=sucursal_id; self.usuario=usuario
    def get_stock(self, producto_id, sucursal_id=None):
        r=self.conn.execute("SELECT COALESCE(existencia,0) FROM productos WHERE id=?",(producto_id,)).fetchone()
        return float(r[0]) if r else 0.0
    def get_low_stock(self, sucursal_id=None):
        return [dict(r) for r in self.conn.execute(
            "SELECT id,nombre,existencia,stock_minimo,unidad FROM productos WHERE activo=1 AND existencia<=stock_minimo AND stock_minimo>0"
        ).fetchall()]
    def get_movements(self, producto_id=None, sucursal_id=None, since=None, limit=200):
        where,params=[],[]
        if producto_id: where.append("producto_id=?"); params.append(producto_id)
        if sucursal_id: where.append("sucursal_id=?"); params.append(sucursal_id)
        if since: where.append("fecha>=?"); params.append(since)
        sql="SELECT * FROM movimientos_inventario"
        if where: sql+=" WHERE "+" AND ".join(where)
        return [dict(r) for r in self.conn.execute(sql+f" ORDER BY fecha DESC LIMIT {limit}",params).fetchall()]
    def register_movement(self, producto_id, movement_type, quantity, reference=None, cost_unit=0, sucursal_id=None, notas=None):
        if movement_type not in MOVEMENT_TYPES: raise InventoryError(f"Tipo invalido: {movement_type}")
        if quantity<=0: raise InventoryError("Cantidad positiva requerida")
        sid=sucursal_id or self.sucursal_id
        tipo_mapa={"purchase":"ENTRADA","sale":"SALIDA","adjustment":"AJUSTE","waste":"MERMA","production":"PRODUCCION","return":"DEVOLUCION","transfer":"TRASPASO"}
        es_salida=movement_type in ("sale","waste","transfer")
        delta=-quantity if es_salida else quantity
        with transaction(self.conn) as c:
            row=c.execute("SELECT existencia,nombre FROM productos WHERE id=?",(producto_id,)).fetchone()
            if not row: raise InventoryError(f"Producto {producto_id} no existe")
            stock_ant=float(row[0] or 0); nombre=row[1]
            if es_salida and stock_ant<quantity: raise StockInsuficienteError(nombre,stock_ant,quantity)
            stock_nuevo=round(stock_ant+delta,4)
            if stock_nuevo < 0:
                raise StockInsuficienteError(nombre, stock_ant, quantity)
            mid=c.execute("""INSERT INTO movimientos_inventario
                (uuid,producto_id,tipo,tipo_movimiento,cantidad,existencia_anterior,existencia_nueva,
                 costo_unitario,costo_total,descripcion,referencia,usuario,sucursal_id,fecha)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",(
                str(uuid.uuid4()),producto_id,tipo_mapa[movement_type],movement_type,quantity,
                stock_ant,stock_nuevo,cost_unit,cost_unit*quantity,
                notas or movement_type,reference,self.usuario,sid)).lastrowid
            c.execute("UPDATE productos SET existencia=? WHERE id=?",(stock_nuevo,producto_id))
            # Sync inventario_actual (per-branch cache used by inventory module)
            c.execute("""
                INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad, costo_promedio)
                VALUES (?,?,?,?)
                ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                    cantidad=excluded.cantidad,
                    ultima_actualizacion=datetime('now')
            """, (producto_id, sid, stock_nuevo, cost_unit))
        return mid
    def adjust_stock(self, producto_id, new_qty, reason="Ajuste", sucursal_id=None):
        """Ajusta el stock al valor exacto new_qty, creando movimiento de ajuste."""
        new_qty = float(new_qty)
        if new_qty < 0:
            raise InventoryError(
                f"No se permite stock negativo (producto_id={producto_id}, nuevo_stock={new_qty:.3f})."
            )
        current = self.get_stock(producto_id)
        diff = new_qty - current
        if abs(diff) < 1e-9:
            return
        if diff > 0:
            # Necesitamos subir el stock: usamos 'purchase' con delta positivo
            self.register_movement(producto_id, "purchase", diff,
                                   reference=reason, sucursal_id=sucursal_id,
                                   notas=f"Ajuste: {current:.3f} -> {new_qty:.3f}")
        else:
            # Necesitamos bajar el stock de forma explícita sin permitir valores negativos.
            from core.db.connection import transaction
            import uuid as _uuid
            with transaction(self.conn) as c:
                stock_nuevo = round(new_qty, 4)
                if stock_nuevo < 0:
                    raise InventoryError(
                        f"No se permite stock negativo (producto_id={producto_id}, nuevo_stock={stock_nuevo:.3f})."
                    )
                c.execute("""INSERT INTO movimientos_inventario
                    (uuid,producto_id,tipo,tipo_movimiento,cantidad,existencia_anterior,existencia_nueva,
                     descripcion,referencia,usuario,sucursal_id,fecha)
                    VALUES(?,?,'AJUSTE','adjustment',?,?,?,?,?,?,?,datetime('now'))""",
                    (str(_uuid.uuid4()), producto_id, abs(diff),
                     current, stock_nuevo,
                     reason or "Ajuste", reason, self.usuario, sucursal_id or self.sucursal_id))
                c.execute("UPDATE productos SET existencia=? WHERE id=?", (stock_nuevo, producto_id))
    def validate_stock(self, producto_id, quantity, sucursal_id=None):
        return self.get_stock(producto_id)>=quantity

    def process_movement(self, product_id, quantity, movement_type,
                         reference=None, metadata=None,
                         branch_id=None, operation_id=None,
                         reference_id=None, reference_type=None,
                         batch_id=None, conn=None, **_extra):
        """
        Wrapper universal de movimientos de inventario.

        API nueva:  process_movement(product_id=x, quantity=1.5, movement_type="purchase")
        API legacy: process_movement(product_id=x, branch_id=b, quantity=-1.5,
                                     movement_type="VENTA", operation_id=op, conn=c)

        quantity : positivo = entrada, negativo = salida.
        conn     : si se provee, ejecuta en esa conexión (transacción del caller).
        Non-fatal para el evento EventBus — nunca cancela la escritura a DB.
        """
        if metadata is None:
            metadata = {}

        delta = float(quantity)
        qty_abs = abs(delta)
        sucursal_id = branch_id if branch_id is not None else self.sucursal_id
        ref = reference or reference_id

        _TIPO_MAP = {
            "purchase": "ENTRADA", "sale": "SALIDA", "adjustment": "AJUSTE",
            "waste": "MERMA", "production": "PRODUCCION", "return": "DEVOLUCION",
            "transfer": "TRASPASO",
            "TRANSFER_IN": "ENTRADA",    "TRANSFER_OUT": "SALIDA",
            "TRANSFER_DISPATCH": "SALIDA", "TRANSFER_RECEIVE": "ENTRADA",
            "VENTA": "SALIDA",           "SALE_CANCEL": "ENTRADA",
            "PRODUCCION_CONSUMO": "SALIDA", "PRODUCCION_GENERACION": "ENTRADA",
        }
        tipo_col = _TIPO_MAP.get(movement_type, "ENTRADA" if delta >= 0 else "SALIDA")

        _mid_holder = [None]

        def _write(c):
            row = c.execute(
                "SELECT existencia, nombre FROM productos WHERE id=?", (product_id,)
            ).fetchone()
            if not row:
                raise InventoryError(f"Producto {product_id} no existe")
            stock_ant = float(row[0] or 0)
            nombre = row[1]
            stock_nuevo = round(stock_ant + delta, 4)
            if stock_nuevo < -1e-6:
                raise StockInsuficienteError(nombre, stock_ant, qty_abs)
            stock_nuevo = max(0.0, stock_nuevo)

            _mid_holder[0] = c.execute("""
                INSERT INTO movimientos_inventario
                    (uuid, producto_id, tipo, tipo_movimiento, cantidad,
                     existencia_anterior, existencia_nueva,
                     descripcion, referencia, usuario, sucursal_id, fecha)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (
                str(uuid.uuid4()), product_id, tipo_col, movement_type, qty_abs,
                stock_ant, stock_nuevo,
                metadata.get("notas") or movement_type,
                str(ref) if ref else None,
                self.usuario, sucursal_id,
            )).lastrowid

            c.execute(
                "UPDATE productos SET existencia=? WHERE id=?",
                (stock_nuevo, product_id)
            )
            c.execute("""
                INSERT INTO inventario_actual
                    (producto_id, sucursal_id, cantidad, costo_promedio)
                VALUES (?,?,?,0)
                ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                    cantidad=excluded.cantidad,
                    ultima_actualizacion=datetime('now')
            """, (product_id, sucursal_id, stock_nuevo))

        if conn is not None:
            _write(conn)
        else:
            with transaction(self.conn) as c:
                _write(c)

        mid = _mid_holder[0]
        try:
            from core.events.event_bus import get_bus
            get_bus().publish("inventory_movement", {
                "movement_id": mid,
                "product_id": product_id,
                "quantity": delta,
                "movement_type": movement_type,
                "reference": str(ref) if ref else None,
                "sucursal_id": sucursal_id,
                "metadata": metadata,
            })
        except Exception as _e:
            logger.warning("process_movement event non-fatal: %s", _e)
        return mid
