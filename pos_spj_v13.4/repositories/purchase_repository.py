
# repositories/purchase_repository.py
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class PurchaseRepository:
    """
    Capa de acceso a datos para el Módulo de Compras (Ingreso de mercancía).
    Escribe en las tablas 'compras' y 'detalles_compra'.
    """
    def __init__(self, db_conn):
        self.db = db_conn

    def create_purchase(self, branch_id: int = 1, user: str = "Sistema",
                        provider_id: int = 0,
                        subtotal: float = 0, tax: float = 0,
                        total: float = 0,
                        operation_id: str = "",
                        notes: str = "",
                        status: str = "completada",
                        **kwargs) -> tuple:
        """
        Crea la cabecera de la compra al proveedor.
        Usa los campos reales de la tabla compras:
          folio, proveedor_id, usuario, subtotal, iva, total, estado, forma_pago, observaciones, factura
        """
        cursor = self.db.cursor()
        folio = f"CMP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        query = """
            INSERT INTO compras
                (folio, proveedor_id, usuario, subtotal, iva, total,
                 estado, forma_pago, observaciones, sucursal_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(query, (
            folio, provider_id, user, subtotal,
            tax, total, status,
            kwargs.get('payment_method', 'CONTADO'),
            notes or operation_id,
            branch_id,
        ))
        
        purchase_id = cursor.lastrowid
        logger.debug(f"Cabecera de compra {folio} insertada con ID {purchase_id}.")
        
        return purchase_id, folio

    def save_purchase_items(self, purchase_id: int, items: list) -> None:
        """Alias for batch — calls save_purchase_item for each item."""
        for it in items:
            self.save_purchase_item(
                purchase_id,
                it.get("product_id", it.get("producto_id", 0)),
                it.get("qty", it.get("cantidad", 1)),
                it.get("unit_cost", it.get("costo_unitario", 0)),
                it.get("qty", it.get("cantidad", 1)) * it.get("unit_cost", it.get("costo_unitario", 0)))

    def save_purchase_item(self, purchase_id: int, product_id: int, qty: float, unit_cost: float, subtotal: float):
        """
        Guarda el detalle de los productos comprados (Ej. 50kg de Pollo Entero a $35/kg).
        """
        cursor = self.db.cursor()
        
        query = """
            INSERT INTO detalles_compra (compra_id, producto_id, cantidad, precio_unitario, subtotal)
            VALUES (?, ?, ?, ?, ?)
        """
        
        cursor.execute(query, (purchase_id, product_id, qty, unit_cost, subtotal))
        logger.debug(f"Detalle de compra insertado: Compra {purchase_id} | Prod {product_id} | Cant {qty}")

    def get_purchase_by_folio(self, folio: str) -> dict:
        """
        Consulta una compra específica por su folio para auditoría o devoluciones.
        """
        cursor = self.db.cursor()
        row = cursor.execute("SELECT * FROM compras WHERE folio = ?", (folio,)).fetchone()
        
        if not row:
            return None
            
        compra = dict(row)
        
        detalles = cursor.execute("""
            SELECT d.*, p.nombre 
            FROM detalles_compra d
            JOIN productos p ON d.producto_id = p.id
            WHERE d.compra_id = ?
        """, (compra['id'],)).fetchall()
        
        compra['items'] = [dict(d) for d in detalles]
        return compra