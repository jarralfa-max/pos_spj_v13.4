
# core/services/inventory/unified_inventory_service.py — SPJ POS v7
from __future__ import annotations
from backend.shared.ids import new_uuid
import logging, uuid
from typing import List
from core.db.connection import get_connection, transaction
logger = logging.getLogger("spj.inventory")


def _sync_branch_inventory(c, prod_id: int, sid: int, delta: float) -> None:
    """Sync branch_inventory; handles schemas with or without batch_id column."""
    if abs(delta) < 1e-9:
        return
    if delta > 0:
        try:
            updated = c.execute(
                "UPDATE branch_inventory SET quantity = quantity + ?, updated_at = datetime('now') "
                "WHERE product_id = ? AND branch_id = ? AND batch_id IS NULL",
                (delta, prod_id, sid)
            ).rowcount
            if not updated:
                c.execute(
                    "INSERT OR IGNORE INTO branch_inventory "
                    "(product_id, branch_id, quantity, batch_id, updated_at) "
                    "VALUES (?, ?, ?, NULL, datetime('now'))",
                    (prod_id, sid, delta)
                )
        except Exception:
            try:
                updated = c.execute(
                    "UPDATE branch_inventory SET quantity = quantity + ?, updated_at = datetime('now') "
                    "WHERE product_id = ? AND branch_id = ?",
                    (delta, prod_id, sid)
                ).rowcount
                if not updated:
                    c.execute(
                        "INSERT OR IGNORE INTO branch_inventory "
                        "(product_id, branch_id, quantity, updated_at) "
                        "VALUES (?, ?, ?, datetime('now'))",
                        (prod_id, sid, delta)
                    )
            except Exception:
                pass  # branch_inventory table doesn't exist in this schema
    else:
        qty = abs(delta)
        try:
            updated = c.execute(
                "UPDATE branch_inventory SET quantity = MAX(0, quantity - ?), updated_at = datetime('now') "
                "WHERE product_id = ? AND branch_id = ? AND batch_id IS NULL",
                (qty, prod_id, sid)
            ).rowcount
            if not updated:
                c.execute(
                    "INSERT OR IGNORE INTO branch_inventory "
                    "(product_id, branch_id, quantity, batch_id, updated_at) "
                    "VALUES (?, ?, 0, NULL, datetime('now'))",
                    (prod_id, sid)
                )
        except Exception:
            try:
                c.execute(
                    "UPDATE branch_inventory SET quantity = MAX(0, quantity - ?), updated_at = datetime('now') "
                    "WHERE product_id = ? AND branch_id = ?",
                    (qty, prod_id, sid)
                )
            except Exception:
                pass
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
        sid = sucursal_id or self.sucursal_id
        try:
            ia_row = self.conn.execute(
                "SELECT COALESCE(quantity, 0) FROM inventory_stock "
                "WHERE product_id=? AND branch_id=?",
                (producto_id, sid),
            ).fetchone()
            if ia_row is not None:
                return float(ia_row[0])
        except Exception:
            pass
        r = self.conn.execute(
            "SELECT COALESCE(existencia, 0) FROM productos WHERE id=?", (producto_id,)
        ).fetchone()
        return float(r[0]) if r else 0.0

    def get_stock_sucursal(self, producto_id, branch_id=None):
        """Retorna stock del producto para la sucursal, priorizando inventory_stock."""
        sid = branch_id or self.sucursal_id
        return self.get_stock(producto_id, sucursal_id=sid)

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
                new_uuid(),producto_id,tipo_mapa[movement_type],movement_type,quantity,
                stock_ant,stock_nuevo,cost_unit,cost_unit*quantity,
                notas or movement_type,reference,self.usuario,sid)).lastrowid
            c.execute("UPDATE productos SET existencia=? WHERE id=?",(stock_nuevo,producto_id))
            # Sync inventory_stock con costo promedio ponderado
            if cost_unit > 0 and delta > 0:
                _cr = c.execute(
                    "SELECT COALESCE(costo_promedio,0) FROM inventory_stock "
                    "WHERE product_id=? AND branch_id=?", (producto_id, sid)
                ).fetchone()
                _ca = float(_cr[0]) if _cr else 0.0
                _cn = round((stock_ant * _ca + quantity * cost_unit) / stock_nuevo, 4) if stock_nuevo > 0 else cost_unit
            else:
                _cn = None

            if _cn is not None:
                c.execute("""
                    INSERT INTO inventory_stock (product_id, branch_id, quantity, costo_promedio)
                    VALUES (?,?,?,?)
                    ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                        cantidad=excluded.cantidad,
                        costo_promedio=excluded.costo_promedio,
                        ultima_actualizacion=datetime('now')
                """, (producto_id, sid, stock_nuevo, _cn))
            else:
                c.execute("""
                    INSERT INTO inventory_stock (product_id, branch_id, quantity, costo_promedio)
                    VALUES (?,?,?,0)
                    ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                        cantidad=excluded.cantidad,
                        ultima_actualizacion=datetime('now')
                """, (producto_id, sid, stock_nuevo))
            _sync_branch_inventory(c, producto_id, sid, delta)

            # Sync inventory_stock so canonical read model stays in sync
            try:
                _ur = c.execute(
                    "SELECT COALESCE(unidad,'kg') FROM productos WHERE id=?", (producto_id,)
                ).fetchone()
                c.execute(
                    """
                    INSERT INTO inventory_stock (product_id, branch_id, quantity, unit, updated_at)
                    VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(product_id, branch_id) DO UPDATE SET
                        quantity=excluded.quantity, unit=excluded.unit,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (producto_id, sid, stock_nuevo, str(_ur[0] if _ur else "kg")),
                )
            except Exception:
                pass
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
                    (str(_new_uuid()), producto_id, abs(diff),
                     current, stock_nuevo,
                     reason or "Ajuste", reason, self.usuario, sucursal_id or self.sucursal_id))
                c.execute("UPDATE productos SET existencia=? WHERE id=?", (stock_nuevo, producto_id))
    def validate_stock(self, producto_id, quantity, sucursal_id=None):
        return self.get_stock(producto_id)>=quantity

    def process_movement(self, product_id, quantity, movement_type,
                         reference=None, metadata=None,
                         branch_id=None, operation_id=None,
                         reference_id=None, reference_type=None,
                         batch_id=None, conn=None, user=None, **_extra):
        """
        Wrapper universal de movimientos de inventario.

        API nueva:  process_movement(product_id=x, quantity=1.5, movement_type="purchase")
        API legacy: process_movement(product_id=x, branch_id=b, quantity=-1.5,
                                     movement_type="VENTA", operation_id=op, conn=c)

        quantity : positivo = entrada, negativo = salida.
        conn     : si se provee, ejecuta en esa conexión (transacción del caller).
        user     : sobreescribe self.usuario para este movimiento.
        Non-fatal para el evento EventBus — nunca cancela la escritura a DB.
        """
        if metadata is None:
            metadata = {}

        _effective_user = user if user is not None else self.usuario
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
            prod_row = c.execute(
                "SELECT nombre FROM productos WHERE id=?", (product_id,)
            ).fetchone()
            if not prod_row:
                raise InventoryError(f"Producto {product_id} no existe")
            nombre = prod_row[0]

            # Read branch-specific stock from inventory_stock (canonical).
            # Fall back to productos.existencia only when no branch row exists yet.
            ia_row = c.execute(
                "SELECT COALESCE(quantity, 0) FROM inventory_stock "
                "WHERE product_id=? AND branch_id=?",
                (product_id, sucursal_id),
            ).fetchone()
            if ia_row is not None:
                stock_ant = float(ia_row[0])
            else:
                ex_row = c.execute(
                    "SELECT COALESCE(existencia, 0) FROM productos WHERE id=?",
                    (product_id,),
                ).fetchone()
                stock_ant = float(ex_row[0]) if ex_row else 0.0

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
                new_uuid(), product_id, tipo_col, movement_type, qty_abs,
                stock_ant, stock_nuevo,
                metadata.get("notas") or movement_type,
                str(ref) if ref else None,
                _effective_user, sucursal_id,
            )).lastrowid
            # FIX FALLA-6: actualizar costo_promedio cuando se provee metadata con unit_cost
            _unit_cost = float(metadata.get("unit_cost") or metadata.get("costo_unitario") or 0)
            if _unit_cost > 0 and delta > 0:
                # Costo promedio ponderado: (stock_ant*costo_ant + qty*costo_nuevo) / stock_nuevo
                _costo_row = c.execute(
                    "SELECT COALESCE(costo_promedio, 0) FROM inventory_stock "
                    "WHERE product_id=? AND branch_id=?", (product_id, sucursal_id)
                ).fetchone()
                _costo_ant = float(_costo_row[0]) if _costo_row else 0.0
                if stock_nuevo > 0:
                    _costo_nuevo = round(
                        (stock_ant * _costo_ant + qty_abs * _unit_cost) / stock_nuevo, 4
                    )
                else:
                    _costo_nuevo = _unit_cost
            else:
                _costo_nuevo = None  # no cambiar costo si no se provee

            if _costo_nuevo is not None:
                c.execute("""
                    INSERT INTO inventory_stock
                        (producto_id, sucursal_id, cantidad, costo_promedio)
                    VALUES (?,?,?,?)
                    ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                        cantidad=excluded.cantidad,
                        costo_promedio=excluded.costo_promedio,
                        ultima_actualizacion=datetime('now')
                """, (product_id, sucursal_id, stock_nuevo, _costo_nuevo))
            else:
                c.execute("""
                    INSERT INTO inventory_stock
                        (producto_id, sucursal_id, cantidad, costo_promedio)
                    VALUES (?,?,?,0)
                    ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                        cantidad=excluded.cantidad,
                        ultima_actualizacion=datetime('now')
                """, (product_id, sucursal_id, stock_nuevo))
            _sync_branch_inventory(c, product_id, sucursal_id, delta)

            # ── Sync inventory_stock (canonical table read by InventoryQueryService) ──
            # This keeps the canonical read model in sync with the legacy write path.
            # Without this, the Inventario module shows stale/zero values after
            # production movements that only write to inventory_stock.
            try:
                unit_row = c.execute(
                    "SELECT COALESCE(unidad,'kg') FROM productos WHERE id=?",
                    (product_id,),
                ).fetchone()
                _unit = str(unit_row[0] if unit_row else "kg")
                c.execute(
                    """
                    INSERT INTO inventory_stock
                        (product_id, branch_id, quantity, unit, updated_at)
                    VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(product_id, branch_id) DO UPDATE SET
                        quantity=excluded.quantity,
                        unit=excluded.unit,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (product_id, sucursal_id, stock_nuevo, _unit),
                )
            except Exception as _e:
                logger.debug("process_movement: inventory_stock sync skipped: %s", _e)

        if conn is not None:
            _write(conn)
        else:
            with transaction(self.conn) as c:
                _write(c)

        mid = _mid_holder[0]
        try:
            import datetime as _dt
            from core.events.event_bus import get_bus, INVENTARIO_ACTUALIZADO
            _bus = get_bus()
            _bus.publish("inventory_movement", {
                "movement_id": mid,
                "product_id": product_id,
                "quantity": delta,
                "movement_type": movement_type,
                "reference": str(ref) if ref else None,
                "sucursal_id": sucursal_id,
                "metadata": metadata,
            })
            # Canonical stock-change event — received by Inventario module to refresh UI
            _bus.publish(INVENTARIO_ACTUALIZADO, {
                "event_type":    INVENTARIO_ACTUALIZADO,
                "sucursal_id":   sucursal_id,
                "producto_ids":  [product_id],
                "origen":        movement_type,
                "referencia_id": str(ref) if ref else None,
                "timestamp":     _dt.datetime.utcnow().isoformat(),
            })
        except Exception as _e:
            logger.warning("process_movement event non-fatal: %s", _e)
        return mid

    apply_movement = process_movement

    # ── Compatibility adapters for legacy InventoryService API ────────────────

    def add_stock(self, product_id: int, branch_id: int, qty: float,
                  unit_cost: float = 0.0, reference_type: str = "purchase",
                  reference_id: str = "", operation_id: str = "",
                  user: str = "sistema", notes: str = "") -> None:
        """Adapter: maps InventoryService.add_stock() → process_movement()."""
        self.process_movement(
            product_id=product_id,
            quantity=qty,
            movement_type=reference_type or "purchase",
            reference=reference_id,
            metadata={"unit_cost": unit_cost, "notas": notes},
            branch_id=branch_id,
            operation_id=operation_id,
            reference_id=reference_id,
            reference_type=reference_type,
            user=user,
        )

    def deduct_stock(self, product_id: int, branch_id: int, qty: float,
                     reference_type: str = "sale", reference_id: str = "",
                     operation_id: str = "", user: str = "sistema",
                     notes: str = "") -> None:
        """Adapter: maps InventoryService.deduct_stock() → process_movement()."""
        self.process_movement(
            product_id=product_id,
            quantity=-qty,
            movement_type=reference_type or "sale",
            reference=reference_id,
            metadata={"notas": notes},
            branch_id=branch_id,
            operation_id=operation_id,
            reference_id=reference_id,
            reference_type=reference_type,
            user=user,
        )

    def descontar_stock(self, producto_id: int, cantidad: float,
                        branch_id: int = 1, referencia_id: str = "EVT",
                        usuario: str = "sistema", **kwargs) -> None:
        """Spanish alias: maps descontar_stock → deduct_stock."""
        self.deduct_stock(
            product_id=producto_id, branch_id=branch_id, qty=cantidad,
            reference_type="SALE_EVENT", reference_id=str(referencia_id),
            operation_id=kwargs.get("operation_id", str(producto_id)),
            user=usuario, notes=kwargs.get("notes", ""),
        )

    def incrementar_stock(self, producto_id: int, cantidad: float,
                          unit_cost: float = 0.0, branch_id: int = 1,
                          referencia_id: str = "EVT",
                          usuario: str = "sistema", **kwargs) -> None:
        """Spanish alias: maps incrementar_stock → add_stock."""
        self.add_stock(
            product_id=producto_id, branch_id=branch_id, qty=cantidad,
            unit_cost=unit_cost,
            reference_type="PURCHASE_EVENT", reference_id=str(referencia_id),
            operation_id=kwargs.get("operation_id", str(producto_id)),
            user=usuario, notes=kwargs.get("notes", ""),
        )

    def ajustar_merma(self, producto_id: int, cantidad: float,
                      branch_id: int = 1, referencia_id: str = "MERMA",
                      usuario: str = "sistema", **kwargs) -> None:
        """Waste adjustment: maps ajustar_merma → process_movement(waste)."""
        self.process_movement(
            product_id=producto_id,
            quantity=-cantidad,
            movement_type="waste",
            reference=str(referencia_id),
            metadata={"notas": kwargs.get("notes", "merma")},
            branch_id=branch_id,
            operation_id=kwargs.get("operation_id", str(producto_id)),
            reference_id=str(referencia_id),
            reference_type="WASTE",
            user=usuario,
        )
