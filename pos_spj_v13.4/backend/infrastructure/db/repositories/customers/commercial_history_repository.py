"""Historial comercial de un cliente (§28, CRM-43) — lecturas de las fuentes
canónicas de otros contextos, nunca escrituras:

* compras / pagos / devoluciones → ``sales``, ``sale_payments``,
  ``sale_returns``, ``sale_lines`` (Ventas, ``customer_id`` canónico);
* pedidos → ``customer_orders`` (Pedidos y Delivery);
* cotizaciones → ``cotizaciones`` (aún con la identidad legacy
  ``cliente_id``; se correlaciona por ``customers.legacy_customer_id``).

Una tabla ausente (instalación sin ese módulo) aporta cero renglones.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase


class CommercialHistoryRepository(CustomerRepositoryBase):
    def _has(self, table: str) -> bool:
        return bool(self._query("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name=?",
                                (table,)))

    def purchases(self, customer_id: str, *, limit: int = 300) -> list[dict]:
        if not self._has("sales"):
            return []
        returns = ("(SELECT COALESCE(SUM(CAST(r.amount AS REAL)), 0) FROM sale_returns r"
                   " WHERE r.sale_id = s.id)") if self._has("sale_returns") else "0"
        lines = ("(SELECT COUNT(*) FROM sale_lines l WHERE l.sale_id = s.id)"
                 if self._has("sale_lines") else "0")
        return self._query(
            f"SELECT s.id, s.sale_number, s.status, s.total, s.branch_id, s.channel,"
            f" COALESCE(s.completed_at, s.created_at) AS occurred_at, s.cashier_user_id,"
            f" {returns} AS returned_amount, {lines} AS line_count"
            " FROM sales s WHERE s.customer_id=? AND s.status IN ('COMPLETED','REVERSED')"
            " ORDER BY occurred_at DESC LIMIT ?", (customer_id, limit))

    def payments(self, customer_id: str, *, limit: int = 300) -> list[dict]:
        if not (self._has("sales") and self._has("sale_payments")):
            return []
        return self._query(
            "SELECT p.id, s.sale_number, p.method, p.amount, p.reference, p.captured_at"
            " FROM sale_payments p JOIN sales s ON s.id = p.sale_id"
            " WHERE s.customer_id=? AND s.status IN ('COMPLETED','REVERSED')"
            " ORDER BY p.captured_at DESC LIMIT ?", (customer_id, limit))

    def returns(self, customer_id: str, *, limit: int = 300) -> list[dict]:
        if not (self._has("sales") and self._has("sale_returns")):
            return []
        name = ("COALESCE(json_extract(l.product_snapshot, '$.name'), '')"
                if self._has("sale_lines") else "''")
        join = "LEFT JOIN sale_lines l ON l.id = r.line_id" if self._has("sale_lines") else ""
        return self._query(
            f"SELECT r.id, s.sale_number, {name} AS product_name, r.quantity, r.amount,"
            f" r.reason, r.created_at FROM sale_returns r JOIN sales s ON s.id = r.sale_id {join}"
            " WHERE s.customer_id=? ORDER BY r.created_at DESC LIMIT ?", (customer_id, limit))

    def orders(self, customer_id: str, *, limit: int = 300) -> list[dict]:
        if not self._has("customer_orders"):
            return []
        return self._query(
            "SELECT id, order_number, channel, fulfillment_type, status, payment_status,"
            " fulfillment_status, grand_total, scheduled_for, created_at"
            " FROM customer_orders WHERE customer_id=? ORDER BY created_at DESC LIMIT ?",
            (customer_id, limit))

    def quotes(self, customer_id: str, *, limit: int = 300) -> list[dict]:
        if not self._has("cotizaciones"):
            return []
        return self._query(
            "SELECT q.id, q.folio, q.total, q.estado, q.fecha, q.fecha_vencimiento"
            " FROM cotizaciones q JOIN customers c ON c.legacy_customer_id = q.cliente_id"
            " WHERE c.id=? ORDER BY q.fecha DESC LIMIT ?", (customer_id, limit))

    def product_affinity(self, customer_id: str, *, limit: int = 50) -> list[dict]:
        if not (self._has("sales") and self._has("sale_lines")):
            return []
        return self._query(
            "SELECT l.product_id,"
            " COALESCE(json_extract(MAX(l.product_snapshot), '$.name'), '') AS product_name,"
            " COALESCE(json_extract(MAX(l.product_snapshot), '$.sku'), '') AS sku,"
            " COUNT(DISTINCT s.id) AS times_bought,"
            " SUM(CAST(l.quantity AS REAL)) AS quantity, MAX(l.quantity_unit) AS unit,"
            " SUM(CAST(l.quantity AS REAL) * CAST(l.unit_price AS REAL)) AS amount,"
            " MAX(COALESCE(s.completed_at, s.created_at)) AS last_bought_at"
            " FROM sale_lines l JOIN sales s ON s.id = l.sale_id"
            " WHERE s.customer_id=? AND s.status='COMPLETED'"
            " GROUP BY l.product_id ORDER BY times_bought DESC, quantity DESC LIMIT ?",
            (customer_id, limit))
