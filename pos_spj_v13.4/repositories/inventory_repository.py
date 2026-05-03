
# repositories/inventory_repository.py
import uuid
import logging

logger = logging.getLogger(__name__)

class InventoryRepository:
    """
    Capa de acceso a datos para el Inventario.
    Maneja las lecturas rápidas (Caché CQRS) y las escrituras inmutables (Event Sourcing).
    """

    def __init__(self, db_conn):
        self.db = db_conn

    def get_current_stock(self, product_id: int, branch_id: int) -> float:
        """
        Lee el stock actual desde la tabla de caché ultrarrápida (inventario_actual).
        """
        query = """
            SELECT cantidad 
            FROM inventario_actual 
            WHERE producto_id = ? AND sucursal_id = ?
        """
        row = self.db.execute(query, (product_id, branch_id)).fetchone()
        return float(row['cantidad']) if row else 0.0

    def get_average_cost(self, product_id: int, branch_id: int) -> float:
        """
        Lee el costo promedio actual desde la tabla de caché.
        """
        query = """
            SELECT costo_promedio 
            FROM inventario_actual 
            WHERE producto_id = ? AND sucursal_id = ?
        """
        row = self.db.execute(query, (product_id, branch_id)).fetchone()
        return float(row['costo_promedio']) if row else 0.0
    
    def get_global_stock_summary(self):
        """
        Obtiene el inventario sumado de TODAS las sucursales.
        Ideal para el 'Módulo Global'.
        """
        query = """
            SELECT 
                p.id, p.nombre, p.unidad,
                SUM(i.cantidad) as total_global,
                AVG(i.costo_promedio) as costo_promedio_global
            FROM inventario_actual i
            JOIN productos p ON p.id = i.producto_id
            GROUP BY p.id, p.nombre, p.unidad
        """
        return self.db.execute(query).fetchall()

    def get_local_stock_summary(self, branch_id: int):
        """
        Obtiene el inventario de UNA sola sucursal.
        Ideal para el 'Módulo Local'.
        """
        query = """
            SELECT 
                p.id, p.nombre, p.unidad,
                i.cantidad as total_local,
                i.costo_promedio
            FROM inventario_actual i
            JOIN productos p ON p.id = i.producto_id
            WHERE i.sucursal_id = ?
        """
        return self.db.execute(query, (branch_id,)).fetchall()

    def insert_movement(self, product_id: int, branch_id: int, movement_type: str, 
                        reference_type: str, reference_id: str, qty: float, unit_cost: float, 
                        operation_id: str, user: str, notes: str = ""):
        """
        Inserta un registro inmutable en el historial (movimientos_inventario).
        """
        query = """
            INSERT INTO movimientos_inventario (
                uuid, producto_id, sucursal_id, tipo_movimiento, referencia_tipo, 
                referencia_id, cantidad, costo_unitario, operation_id, usuario, nota
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        movement_uuid = str(uuid.uuid4())
        
        self.db.execute(query, (
            movement_uuid, 
            product_id, 
            branch_id, 
            movement_type,      # 'IN' o 'OUT'
            reference_type,     # 'SALE', 'PURCHASE', 'PRODUCTION'
            reference_id, 
            qty,                # Positivo para entradas, negativo para salidas
            unit_cost, 
            operation_id, 
            user, 
            notes
        ))

    def update_inventory_cache(self, product_id: int, branch_id: int,
                               new_qty: float, new_avg_cost: float) -> None:
        """
        Actualiza la tabla rápida inventario_actual (UPSERT) y
        sincroniza productos.existencia y precio_compra.
        No usa try/except silencioso — los errores se propagan.
        """
        self.db.execute("""
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad, costo_promedio)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(producto_id, sucursal_id) DO UPDATE
               SET cantidad             = excluded.cantidad,
                   costo_promedio       = excluded.costo_promedio,
                   ultima_actualizacion = datetime('now')
        """, (product_id, branch_id, new_qty, new_avg_cost))

        # Sync branch_inventory — manual upsert: ON CONFLICT(product_id, branch_id)
        # no puede usar UNIQUE(branch_id, product_id, batch_id) cuando batch_id IS NULL.
        _bi_rows = self.db.execute("""
            UPDATE branch_inventory
            SET quantity = ?, updated_at = datetime('now')
            WHERE product_id = ? AND branch_id = ? AND batch_id IS NULL
        """, (new_qty, product_id, branch_id)).rowcount
        if not _bi_rows:
            self.db.execute("""
                INSERT OR IGNORE INTO branch_inventory
                    (product_id, branch_id, quantity, batch_id, updated_at)
                VALUES (?, ?, ?, NULL, datetime('now'))
            """, (product_id, branch_id, new_qty))

        # Sync productos.existencia = sum across all branches
        self.db.execute("""
            UPDATE productos
            SET existencia   = (SELECT COALESCE(SUM(cantidad),0)
                                FROM inventario_actual
                                WHERE producto_id = ?),
                precio_compra = ?
            WHERE id = ?
        """, (product_id, new_avg_cost, product_id))

        logger.debug("Cache actualizado: prod=%s suc=%s qty=%.3f cost=%.4f",
                     product_id, branch_id, new_qty, new_avg_cost)

    def sum_all_movements(self, product_id: int, branch_id: int) -> float:
        """
        Calcula la verdad absoluta sumando todo el historial de movimientos (Auditoría).
        """
        query = """
            SELECT SUM(cantidad) as total_real
            FROM movimientos_inventario
            WHERE producto_id = ? AND sucursal_id = ?
        """
        row = self.db.execute(query, (product_id, branch_id)).fetchone()
        return float(row['total_real']) if row and row['total_real'] is not None else 0.0

    def force_update_inventory_cache_qty(self, product_id: int, branch_id: int, real_stock: float):
        """
        Sobrescribe la cantidad en el caché (usado solo por el botón de pánico/conciliación).
        """
        query = """
            UPDATE inventario_actual 
            SET cantidad = ?, ultima_actualizacion = datetime('now')
            WHERE producto_id = ? AND sucursal_id = ?
        """
        self.db.execute(query, (real_stock, product_id, branch_id))