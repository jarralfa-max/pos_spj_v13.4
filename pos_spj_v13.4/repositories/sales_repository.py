
# repositories/sales_repository.py
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

class SalesRepository:
    """
    Capa de acceso a datos para Ventas.
    Encargada de escribir en las tablas `ventas` y `detalles_venta`.
    No maneja transacciones, eso lo delega al Orquestador (SalesService).
    """
    def __init__(self, db_conn):
        self.db = db_conn

    def create_sale(self, branch_id: int, user: str, client_id: int, subtotal: float, 
                    discount: float, total: float, payment_method: str, amount_paid: float, 
                    operation_id: str, notes: str) -> tuple:
        """
        Crea la cabecera de la venta.
        Retorna una tupla: (sale_id, folio)
        """
        cursor = self.db.cursor()

        # Generar un Folio único con sufijo UUID para evitar colisiones en alta concurrencia.
        # Formato: VNT-YYYYMMDDHHMMSS-XXXX (XXXX = primeros 4 hex del UUID)
        # Verificamos unicidad contra la BD (hasta 5 intentos, luego 8 hex).
        _base = datetime.now().strftime('%Y%m%d%H%M%S')
        folio = f"VNT-{_base}-{uuid.uuid4().hex[:4].upper()}"
        for _attempt in range(4):
            try:
                _exists = cursor.execute(
                    "SELECT 1 FROM ventas WHERE folio=? LIMIT 1", (folio,)
                ).fetchone()
                if not _exists:
                    break
                folio = f"VNT-{_base}-{uuid.uuid4().hex[:4].upper()}"
            except Exception:
                break  # If DB check fails, use current folio (non-critical)
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        query = """
            INSERT INTO ventas (
                folio, sucursal_id, usuario, cliente_id, subtotal,
                descuento, total, forma_pago, efectivo_recibido,
                operation_id, observations, estado, fecha
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completada', ?)
        """

        cursor.execute(query, (
            folio, branch_id, user, client_id, subtotal,
            discount, total, payment_method, amount_paid,
            operation_id, notes, fecha_actual
        ))
        
        sale_id = cursor.lastrowid
        logger.debug(f"Cabecera de venta {folio} insertada con ID {sale_id}.")
        
        return sale_id, folio

    def save_sale_item(self, sale_id: int, product_id: int, qty: float, unit_price: float, subtotal: float):
        """
        Guarda un producto individual dentro del ticket (detalle de venta).
        """
        cursor = self.db.cursor()
        
        query = """
            INSERT INTO detalles_venta (venta_id, producto_id, cantidad, precio_unitario, subtotal)
            VALUES (?, ?, ?, ?, ?)
        """
        
        cursor.execute(query, (sale_id, product_id, qty, unit_price, subtotal))
        logger.debug(f"Detalle insertado: Venta {sale_id} | Prod {product_id} | Cant {qty}")

    def get_sale_by_folio(self, folio: str) -> dict:
        """
        Consulta una venta específica por su folio. Útil para devoluciones o reimpresiones.
        """
        cursor = self.db.cursor()
        row = cursor.execute("SELECT * FROM ventas WHERE folio = ?", (folio,)).fetchone()
        
        if not row:
            return None
            
        venta = dict(row)
        
        # Traer también los detalles
        detalles = cursor.execute("""
            SELECT d.*, p.nombre 
            FROM detalles_venta d
            JOIN productos p ON d.producto_id = p.id
            WHERE d.venta_id = ?
        """, (venta['id'],)).fetchall()
        
        venta['items'] = [dict(d) for d in detalles]
        return venta
        
    def get_sales_summary(self, branch_id: int, date_start: str, date_end: str) -> list:
        """
        Obtiene un resumen de ventas para un rango de fechas. (Para Reportes BI)
        """
        cursor = self.db.cursor()
        query = """
            SELECT folio, total, forma_pago, usuario, fecha 
            FROM ventas 
            WHERE sucursal_id = ? AND fecha BETWEEN ? AND ? AND estado = 'completada'
            ORDER BY fecha DESC
        """
        rows = cursor.execute(query, (branch_id, f"{date_start} 00:00:00", f"{date_end} 23:59:59")).fetchall()
        return [dict(r) for r in rows]