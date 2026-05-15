
# repositories/purchase_repository.py
import logging
import uuid
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
        # Timestamp + 4-char UUID fragment prevents same-second collisions
        folio = f"CMP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
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

    # ── Read helpers ─────────────────────────────────────────────────────────

    def get_header_stats(self, sucursal_id: int = 1) -> dict:
        """Stats for the top KPI bar: compras this month, active providers, pending orders."""
        cur = self.db.cursor()
        r = cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(total),0) FROM compras "
            "WHERE sucursal_id=? AND DATE(fecha)>=DATE('now','start of month')",
            (sucursal_id,),
        ).fetchone()
        count_mes  = int(r[0] or 0)
        total_mes  = float(r[1] or 0)

        r2 = cur.execute(
            "SELECT COUNT(*) FROM proveedores WHERE activo=1"
        ).fetchone()
        prov_activos = int(r2[0] or 0)

        oc_pendientes = 0
        try:
            r3 = cur.execute(
                "SELECT COUNT(*) FROM ordenes_compra WHERE estado='pendiente'"
            ).fetchone()
            oc_pendientes = int(r3[0] or 0)
        except Exception:
            pass

        return {
            "count_mes":      count_mes,
            "total_mes":      total_mes,
            "prov_activos":   prov_activos,
            "oc_pendientes":  oc_pendientes,
        }

    def get_monthly_kpis(self, sucursal_id: int, desde: str, hasta: str) -> dict:
        """Month-range KPIs for history sidebar (count, total, pending_total, provider_count)."""
        cur = self.db.cursor()
        r1 = cur.execute(
            """SELECT COUNT(*), COALESCE(SUM(total),0)
               FROM compras WHERE sucursal_id=? AND fecha BETWEEN ? AND ?""",
            (sucursal_id, desde, hasta),
        ).fetchone()
        r2 = cur.execute(
            """SELECT COALESCE(SUM(total),0)
               FROM compras WHERE sucursal_id=? AND fecha BETWEEN ? AND ?
               AND estado IN ('pendiente','credito')""",
            (sucursal_id, desde, hasta),
        ).fetchone()
        r3 = cur.execute(
            """SELECT COUNT(DISTINCT proveedor_id)
               FROM compras WHERE sucursal_id=? AND fecha BETWEEN ? AND ?""",
            (sucursal_id, desde, hasta),
        ).fetchone()
        return {
            "count":          int(r1[0] or 0) if r1 else 0,
            "total":          float(r1[1] or 0) if r1 else 0.0,
            "pending_total":  float(r2[0] or 0) if r2 else 0.0,
            "provider_count": int(r3[0] or 0) if r3 else 0,
        }

    def get_purchase_detail_items(self, compra_id: int) -> list:
        """Line items for a purchase — used by inline detail panel and full detail dialog."""
        rows = self.db.cursor().execute(
            """SELECT p.nombre, dd.cantidad, dd.costo_unitario, dd.subtotal
               FROM detalles_compra dd
               JOIN productos p ON p.id = dd.producto_id
               WHERE dd.compra_id = ?
               ORDER BY p.nombre""",
            (compra_id,),
        ).fetchall()
        return [
            {
                "nombre":       r[0],
                "cantidad":     float(r[1] or 0),
                "costo_unitario": float(r[2] or 0),
                "subtotal":     float(r[3] or 0),
            }
            for r in rows
        ]

    def get_purchase_state(self, compra_id: int) -> "dict | None":
        """Returns {id, folio, estado} for state-machine guards (cancel / reopen)."""
        row = self.db.cursor().execute(
            "SELECT id, folio, estado FROM compras WHERE id=?", (compra_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "id":     row[0],
            "folio":  str(row[1] or compra_id),
            "estado": str(row[2] or "").lower(),
        }

    def get_purchase_full(self, compra_id: int) -> "dict | None":
        """Full purchase header as dict (for detail/print view)."""
        row = self.db.cursor().execute(
            "SELECT * FROM compras WHERE id=?", (compra_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_provider_name(self, proveedor_id: int) -> str:
        """Provider display name for a given ID."""
        row = self.db.cursor().execute(
            "SELECT nombre FROM proveedores WHERE id=?", (proveedor_id,)
        ).fetchone()
        return str(row[0]) if row else ""

    # ── Write helpers ─────────────────────────────────────────────────────────

    def cancel_purchase(self, compra_id: int) -> None:
        """Sets estado → 'cancelada'. Caller writes audit trail."""
        self.db.execute(
            "UPDATE compras SET estado='cancelada' WHERE id=?", (compra_id,))
        self.db.commit()

    def reopen_purchase(self, compra_id: int) -> None:
        """Sets estado → 'pendiente' (from 'cancelada'). Caller writes audit trail."""
        self.db.execute(
            "UPDATE compras SET estado='pendiente' WHERE id=?", (compra_id,))
        self.db.commit()

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