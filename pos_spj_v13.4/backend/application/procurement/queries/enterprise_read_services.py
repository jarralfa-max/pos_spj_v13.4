"""Read-only query services for the enterprise procurement UI (requisitions,
orders, receipts, invoices). Paginated, no business logic; the UI never issues
SQL — it asks these services for display-ready rows."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.application.procurement.queries.product_names import (
    UNKNOWN_PRODUCT,
    product_labels,
)

from backend.application.procurement.dto.enterprise_dtos import (
    GoodsReceiptLineDTO,
    InvoiceDetailDTO,
    InvoiceLineDTO,
    InvoiceMatchDTO,
    InvoiceRowDTO,
    OrderDetailDTO,
    OrderLineDTO,
    OrderRowDTO,
    OrderVersionDTO,
    ReceiptDetailDTO,
    ReceiptDiscrepancyDTO,
    ReceiptRowDTO,
    RequisitionDetailDTO,
    RequisitionLineDTO,
    RequisitionRowDTO,
)


class _Base:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            cur = self._conn.execute(sql, params)
        except sqlite3.OperationalError:
            return []
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _query_one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _with_actor_names(self, events: list[dict]) -> list[dict]:
        """Agrega ``actor_name`` (nombre del usuario, nunca su id) a la bitácora."""
        names: dict[str, str] = {}
        for event in events:
            actor = event.get("actor_user_id")
            if actor and actor not in names:
                row = self._query_one("SELECT nombre FROM usuarios WHERE id=?", (actor,))
                names[actor] = str(row["nombre"]) if row and row.get("nombre") else "Usuario"
            event["actor_name"] = names.get(actor, "Sistema") if actor else "Sistema"
        return events

    def _scalar(self, sql: str, params: tuple = (), default: Any = 0) -> Any:
        try:
            row = self._conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError:
            return default
        return row[0] if row and row[0] is not None else default


class RequisitionReadService(_Base):
    def count(self, *, status: str | None = None, search: str = "", branch_id=None,
              start_date=None, end_date=None) -> int:
        where, params = _where(("status",), status, search, ("document_number", "branch_id"),
                               branch_id, start_date, end_date)
        return int(self._scalar(
            f"SELECT COUNT(*) FROM purchase_requisitions{where}", tuple(params)))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0, branch_id=None, start_date=None,
             end_date=None) -> list[RequisitionRowDTO]:
        where, params = _where(("status",), status, search, ("document_number", "branch_id"),
                               branch_id, start_date, end_date)
        rows = self._query(
            "SELECT purchase_requisitions.id, document_number, branch_id,"
            " requested_by_user_id, purchase_type, priority, status,"
            " purchase_requisitions.created_at, COALESCE(s.nombre, '—') AS branch_name"
            " FROM purchase_requisitions"
            " LEFT JOIN sucursales s ON s.id = purchase_requisitions.branch_id"
            f"{where} ORDER BY purchase_requisitions.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset))
        return [RequisitionRowDTO(
            id=r["id"], document_number=r["document_number"], branch_id=r["branch_id"],
            branch_name=r["branch_name"], requested_by_user_id=r["requested_by_user_id"],
            purchase_type=r["purchase_type"], priority=r["priority"], status=r["status"],
            created_at=r["created_at"]) for r in rows]

    def _requester_name(self, user_id: str | None) -> str:
        if not user_id:
            return "—"
        user = self._query_one("SELECT nombre FROM usuarios WHERE id=?", (user_id,))
        return str(user["nombre"]) if user else "Usuario no disponible"

    def detail(self, requisition_id: str) -> RequisitionDetailDTO | None:
        row = self._query_one("SELECT * FROM purchase_requisitions WHERE id=?",
                              (requisition_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT id, product_id, quantity, estimated_unit_cost, purchase_nature FROM"
            " purchase_requisition_lines WHERE requisition_id=? ORDER BY id",
            (requisition_id,))
        names = product_labels(self._conn, (lr["product_id"] for lr in line_rows))
        lines = [RequisitionLineDTO(
            id=lr["id"], product_id=lr["product_id"], quantity=lr["quantity"],
            estimated_unit_cost=lr["estimated_unit_cost"],
            purchase_nature=lr["purchase_nature"],
            product_name=names.get(str(lr["product_id"]), UNKNOWN_PRODUCT))
            for lr in line_rows]
        related_documents = (
            self._query(
                "SELECT id,document_number,'RFQ' AS document_type,status,created_at"
                " FROM requests_for_quotation WHERE requisition_id=?", (requisition_id,))
            + self._query(
                "SELECT id,document_number,'PO' AS document_type,status,created_at"
                " FROM purchase_orders WHERE source_requisition_id=?", (requisition_id,))
            + self._query(
                "SELECT id,document_number,'DIRECT_PURCHASE' AS document_type,status,created_at"
                " FROM direct_purchases WHERE source_requisition_id=?", (requisition_id,))
        )
        timeline = self._with_actor_names(self._query(
            "SELECT action,actor_user_id,reason,created_at FROM procurement_audit_log"
            " WHERE document_id=? ORDER BY created_at", (requisition_id,)))
        return RequisitionDetailDTO(
            id=row["id"], document_number=row["document_number"], branch_id=row["branch_id"],
            requested_by_user_id=row["requested_by_user_id"],
            requested_by_name=self._requester_name(row["requested_by_user_id"]),
            purchase_type=row["purchase_type"], priority=row["priority"],
            business_reason=row["business_reason"] or "", status=row["status"],
            source_channel=row["source_channel"], created_at=row["created_at"],
            updated_at=row["updated_at"], required_date=row["required_date"],
            source_reference_id=row["source_reference_id"],
            approved_by_user_id=row["approved_by_user_id"], operation_id=row["operation_id"],
            lines=lines, related_documents=related_documents, timeline=timeline)


_ORDER_HEADER_KEYS = ("payment_terms", "exchange_rate", "required_date", "promised_date",
                      "delivery_method", "delivery_address", "cost_center",
                      "project_reference", "contract_reference", "notes",
                      "supplier_reference", "confirmed_at", "confirmed_delivery_date",
                      "confirmation_exceptions", "confirmation_comments",
                      "origin_supplier_address_id", "origin_address_snapshot")


def _line_subtotal(line: dict) -> str:
    from decimal import Decimal
    quantity = Decimal(str(line.get("ordered_quantity") or "0"))
    price = Decimal(str(line.get("unit_price") or "0"))
    discount = Decimal(str(line.get("discount") or "0"))
    return str(quantity * price - discount)


class OrderReadService(_Base):
    def count(self, *, status: str | None = None, search: str = "", branch_id=None,
              start_date=None, end_date=None) -> int:
        where, params = _where(("status",), status, search, ("document_number", "supplier_id"),
                               branch_id, start_date, end_date)
        return int(self._scalar(f"SELECT COUNT(*) FROM purchase_orders{where}", tuple(params)))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0, branch_id=None, start_date=None,
             end_date=None) -> list[OrderRowDTO]:
        where, params = _where(("status",), status, search, ("document_number", "supplier_id"),
                               branch_id, start_date, end_date)
        rows = self._query(
            "SELECT purchase_orders.id, document_number, supplier_id, branch_id, status, total,"
            " version, currency_code, purchase_orders.created_at,"
            " COALESCE(p.legal_name, '—') AS supplier_name FROM purchase_orders"
            " LEFT JOIN (SELECT id, legal_name FROM supplier_master) p ON p.id = purchase_orders.supplier_id"
            f"{where} ORDER BY purchase_orders.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset))
        return [OrderRowDTO(
            id=r["id"], document_number=r["document_number"], supplier_id=r["supplier_id"],
            supplier_name=r["supplier_name"], branch_id=r["branch_id"], status=r["status"],
            total=r["total"], version=r["version"], currency_code=r["currency_code"],
            created_at=r["created_at"]) for r in rows]

    def _lookup(self, sql: str, key) -> str:
        """Nombre para mostrar; «—» si no hay dato o la tabla no existe."""
        if not key:
            return "—"
        row = self._query_one(sql, (key,))
        return str(next(iter(row.values()))) if row else "—"

    def _supplier_name(self, supplier_id: str | None) -> str:
        if not supplier_id:
            return "—"
        supplier = self._query_one("SELECT legal_name FROM supplier_master WHERE id=?", (supplier_id,))
        return str(supplier["legal_name"]) if supplier else "Proveedor no disponible"

    def detail(self, order_id: str) -> OrderDetailDTO | None:
        row = self._query_one("SELECT * FROM purchase_orders WHERE id=?", (order_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT * FROM purchase_order_lines WHERE purchase_order_id=? ORDER BY id",
            (order_id,))
        names = product_labels(self._conn, (lr["product_id"] for lr in line_rows))
        lines = [OrderLineDTO(
            product_id=lr["product_id"], description=lr["description"] or "",
            ordered_quantity=lr["ordered_quantity"], unit_price=lr["unit_price"],
            received_quantity=lr["received_quantity"],
            accepted_quantity=lr["accepted_quantity"],
            product_name=(names.get(str(lr["product_id"])) or lr["description"]
                          or UNKNOWN_PRODUCT),
            purchase_unit=lr.get("purchase_unit") or "", id=lr["id"],
            inventory_unit=lr.get("inventory_unit") or "",
            conversion_factor=lr.get("conversion_factor") or "1",
            discount=lr.get("discount") or "0", tax=lr.get("tax") or "0",
            subtotal=_line_subtotal(lr), confirmed_quantity=lr.get("confirmed_quantity"),
            destination_warehouse_id=lr.get("destination_warehouse_id"))
            for lr in line_rows]
        version_rows = self._query(
            "SELECT version, reason, changed_by_user_id, created_at FROM"
            " purchase_order_versions WHERE purchase_order_id=? ORDER BY version",
            (order_id,))
        versions = [OrderVersionDTO(
            version=vr["version"], reason=vr["reason"] or "",
            changed_by_user_id=vr["changed_by_user_id"], created_at=vr["created_at"])
            for vr in version_rows]
        related_documents = self._query(
            "SELECT id,document_number,'INVOICE' AS document_type,status,created_at"
            " FROM supplier_invoices WHERE purchase_order_id=?", (order_id,))
        timeline = self._with_actor_names(self._query(
            "SELECT action,actor_user_id,reason,created_at FROM procurement_audit_log"
            " WHERE document_id=? ORDER BY created_at", (order_id,)))
        return OrderDetailDTO(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], supplier_name=self._supplier_name(row["supplier_id"]),
            branch_id=row["branch_id"], warehouse_id=row["warehouse_id"],
            currency_code=row["currency_code"], purchase_type=row["purchase_type"],
            status=row["status"], total=row["total"], version=row["version"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"],
            source_requisition_id=row["source_requisition_id"],
            source_rfq_id=row["source_rfq_id"], source_award_id=row["source_award_id"],
            operation_id=row["operation_id"], lines=lines, versions=versions,
            related_documents=related_documents, timeline=timeline,
            **{key: (None if row.get(key) in (None, "") else str(row.get(key)))
               for key in _ORDER_HEADER_KEYS},
            branch_name=self._lookup("SELECT nombre FROM sucursales WHERE id=?",
                                     row["branch_id"]),
            warehouse_name=self._lookup("SELECT name FROM warehouses WHERE id=?",
                                        row["warehouse_id"]),
            buyer_name=self._lookup("SELECT nombre FROM usuarios WHERE id=?",
                                    row.get("created_by_user_id")))


class InvoiceReadService(_Base):
    def billable_documents(self, *, branch_id: str | None = None, search="",
                           limit=50) -> list[dict]:
        """Órdenes y compras con mercancía recibida, de CUALQUIER sucursal:
        las compras son globales (decisión del usuario). Antes sólo aparecían
        las de la sucursal de la sesión, y la factura de una orden con destino
        a otra sucursal no se podía capturar desde aquí."""
        like = f"%{search.strip()}%"
        return self._query(
            "SELECT o.id,o.document_number,o.supplier_id,p.legal_name,'PURCHASE_ORDER' document_type"
            " FROM purchase_orders o JOIN (SELECT id, legal_name FROM supplier_master) p ON p.id=o.supplier_id"
            " WHERE o.status IN ('PARTIALLY_RECEIVED','RECEIVED')"
            " AND (o.document_number LIKE ? OR p.legal_name LIKE ?) UNION ALL"
            " SELECT d.id,d.document_number,d.supplier_id,p.legal_name,'DIRECT_PURCHASE'"
            " FROM direct_purchases d JOIN (SELECT id, legal_name FROM supplier_master) p ON p.id=d.supplier_id"
            " WHERE d.status IN ('PARTIALLY_RECEIVED','RECEIVED')"
            " AND (d.document_number LIKE ? OR p.legal_name LIKE ?) LIMIT ?",
            (like, like, like, like, limit))

    def billable_lines(self, document_type: str, document_id: str) -> list[dict]:
        """Lo que la conciliación esperará de cada línea (mismas reglas que
        `MatchSupplierInvoiceUseCase`): aceptado por línea, ya facturado,
        pendiente de facturar, precio NETO de descuento e impuesto declarado
        prorrateado a lo pendiente."""
        from decimal import Decimal

        from backend.domain.procurement.receiving_matching_policies import (
            allocate_accepted_quantities,
        )

        def dec(value) -> Decimal:
            try:
                return Decimal(str(value if value not in (None, "") else "0"))
            except Exception:
                return Decimal("0")

        def plain(value: Decimal) -> str:
            return format(value.normalize(), "f")

        is_order = document_type == "PURCHASE_ORDER"
        if is_order:
            rows = self._query(
                # A $/kg (peso variable) se factura en kg: lo pactado son los kg
                # nominales y lo aceptado, el PESO REAL de las recepciones.
                "SELECT id source_line_id,product_id,description,ordered_quantity quantity,"
                " unit_price,discount,tax,"
                " CASE WHEN pricing_basis='PER_KILOGRAM' THEN 'KG' ELSE purchase_unit END"
                "  purchase_unit,"
                " CASE WHEN pricing_basis='PER_KILOGRAM'"
                "  THEN CAST(ordered_quantity AS NUMERIC)*CAST(conversion_factor AS NUMERIC)"
                "  ELSE ordered_quantity END billable_quantity,"
                " ordered_quantity inventory_quantity, pricing_basis"
                " FROM purchase_order_lines"
                " WHERE purchase_order_id=? ORDER BY id", (document_id,))
            receipt_filter, invoice_key = "g.purchase_order_id=?", "purchase_order_line_id"
        else:
            rows = self._query(
                # Su recepción está en unidad de INVENTARIO (cantidad × factor,
                # o el peso real); se factura lo facturable (cantidad o, con
                # precio por kg, el peso real).
                "SELECT id source_line_id,product_id,description,quantity,"
                " unit_cost unit_price,discount,tax,"
                " CASE WHEN pricing_basis='PER_KILOGRAM' THEN 'KG' ELSE purchase_unit END"
                "  purchase_unit,"
                " CASE WHEN pricing_basis='PER_KILOGRAM' AND net_weight IS NOT NULL"
                "  THEN net_weight ELSE quantity END billable_quantity,"
                " CASE WHEN inventory_by_weight=1 AND net_weight IS NOT NULL THEN net_weight"
                "  ELSE CAST(quantity AS NUMERIC)*CAST(conversion_factor AS NUMERIC) END"
                "  inventory_quantity FROM direct_purchase_lines"
                " WHERE direct_purchase_id=? ORDER BY id", (document_id,))
            receipt_filter, invoice_key = "g.direct_purchase_id=?", "direct_purchase_line_id"
        by_line: dict[str, Decimal] = {}
        unlinked: dict[str, Decimal] = {}
        for r in self._query(
                "SELECT r.product_id, r.purchase_order_line_id, r.accepted_quantity"
                " FROM goods_receipt_lines r JOIN goods_receipts g ON g.id=r.goods_receipt_id"
                f" WHERE {receipt_filter} AND g.status='COMPLETED'", (document_id,)):
            key = r.get("purchase_order_line_id")
            bucket = by_line if key else unlinked
            key = key or r["product_id"]
            bucket[key] = bucket.get(key, Decimal("0")) + dec(r["accepted_quantity"])
        def ratio(r) -> Decimal:
            """Unidades de inventario recibidas por cada unidad facturable."""
            billable = dec(r["billable_quantity"])
            return dec(r["inventory_quantity"]) / billable if billable > 0 else Decimal("1")

        accepted = allocate_accepted_quantities(
            [(r["source_line_id"], r["product_id"], dec(r["inventory_quantity"]))
             for r in rows], by_line, unlinked)
        weights: dict[str, Decimal] = {}
        if is_order:
            for w in self._query(
                    "SELECT r.purchase_order_line_id, r.net_weight, r.received_quantity,"
                    " r.accepted_quantity FROM goods_receipt_lines r"
                    " JOIN goods_receipts g ON g.id=r.goods_receipt_id"
                    " WHERE g.purchase_order_id=? AND g.status='COMPLETED'"
                    " AND r.net_weight IS NOT NULL", (document_id,)):
                received = dec(w["received_quantity"])
                if received > 0 and w.get("purchase_order_line_id"):
                    weights[w["purchase_order_line_id"]] = (
                        weights.get(w["purchase_order_line_id"], Decimal("0"))
                        + dec(w["net_weight"]) * dec(w["accepted_quantity"]) / received)
        result = []
        for r in rows:
            quantity = dec(r["billable_quantity"])
            invoiced = dec(self._scalar(
                "SELECT SUM(CAST(l.invoiced_quantity AS NUMERIC)) FROM supplier_invoice_lines l"
                " JOIN supplier_invoices i ON i.id=l.supplier_invoice_id"
                f" WHERE l.{invoice_key}=? AND i.status<>'CANCELLED'",
                (r["source_line_id"],), default=0))
            if r.get("pricing_basis") == "PER_KILOGRAM":
                line_accepted = weights.get(r["source_line_id"], Decimal("0"))
            else:
                line_accepted = accepted.get(r["source_line_id"], Decimal("0")) / ratio(r)
            pending = max(Decimal("0"), line_accepted - invoiced)
            price = dec(r["unit_price"])
            net = (quantity * price - dec(r["discount"])) / quantity if quantity > 0 else price
            tax = dec(r["tax"])
            declared = tax > 0 or not is_order
            tax_pending = (tax / quantity * pending) if quantity > 0 and declared else Decimal("0")
            result.append({
                "source_line_id": r["source_line_id"], "product_id": r["product_id"],
                "description": r.get("description") or "", "quantity": plain(quantity),
                "purchase_unit": r.get("purchase_unit") or "",
                "unit_price": plain(net.quantize(Decimal("0.0001"))),
                "tax": str(tax_pending.quantize(Decimal("0.01"))),
                "tax_declared": declared,
                "accepted_quantity": plain(line_accepted),
                "invoiced_quantity": str(invoiced),
                "pending_quantity": plain(pending),
            })
        return result

    def resolve_billable_document(self, document_id: str) -> dict | None:
        """Identify a billable document's type + supplier without the caller
        having to already know whether it's a PO or a direct purchase."""
        row = self._query_one(
            "SELECT o.supplier_id, COALESCE(p.legal_name,'—') AS supplier_name,"
            " 'PURCHASE_ORDER' AS document_type FROM purchase_orders o"
            " LEFT JOIN (SELECT id, legal_name FROM supplier_master) p ON p.id=o.supplier_id WHERE o.id=?", (document_id,))
        if row is not None:
            return row
        return self._query_one(
            "SELECT d.supplier_id, COALESCE(p.legal_name,'—') AS supplier_name,"
            " 'DIRECT_PURCHASE' AS document_type FROM direct_purchases d"
            " LEFT JOIN (SELECT id, legal_name FROM supplier_master) p ON p.id=d.supplier_id WHERE d.id=?", (document_id,))

    def count(self, *, status: str | None = None, search: str = "", branch_id=None,
              start_date=None, end_date=None) -> int:
        where, params = _where(("status",), status, search,
                               ("document_number", "supplier_id", "invoice_number"),
                               branch_id, start_date, end_date,
                               "(purchase_order_id IN (SELECT id FROM purchase_orders WHERE branch_id=?)"
                               " OR direct_purchase_id IN (SELECT id FROM direct_purchases WHERE branch_id=?))")
        return int(self._scalar(f"SELECT COUNT(*) FROM supplier_invoices{where}", tuple(params)))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0, branch_id=None, start_date=None,
             end_date=None) -> list[InvoiceRowDTO]:
        where, params = _where(("status",), status, search,
                               ("document_number", "supplier_id", "invoice_number"),
                               branch_id, start_date, end_date,
                               "(purchase_order_id IN (SELECT id FROM purchase_orders WHERE branch_id=?)"
                               " OR direct_purchase_id IN (SELECT id FROM direct_purchases WHERE branch_id=?))")
        rows = self._query(
            "SELECT supplier_invoices.id, document_number, supplier_id, invoice_number, total,"
            " currency_code, status, match_result, purchase_order_id,"
            " supplier_invoices.created_at, COALESCE(p.legal_name, '—') AS supplier_name"
            " FROM supplier_invoices"
            " LEFT JOIN (SELECT id, legal_name FROM supplier_master) p ON p.id = supplier_invoices.supplier_id"
            f"{where} ORDER BY supplier_invoices.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset))
        return [InvoiceRowDTO(
            id=r["id"], document_number=r["document_number"], supplier_id=r["supplier_id"],
            supplier_name=r["supplier_name"], invoice_number=r["invoice_number"],
            total=r["total"], currency_code=r["currency_code"], status=r["status"],
            match_result=r["match_result"], purchase_order_id=r["purchase_order_id"],
            created_at=r["created_at"]) for r in rows]

    def _supplier_name(self, supplier_id: str | None) -> str:
        if not supplier_id:
            return "—"
        supplier = self._query_one("SELECT legal_name FROM supplier_master WHERE id=?", (supplier_id,))
        return str(supplier["legal_name"]) if supplier else "Proveedor no disponible"

    def detail(self, invoice_id: str) -> InvoiceDetailDTO | None:
        row = self._query_one("SELECT * FROM supplier_invoices WHERE id=?", (invoice_id,))
        if row is None:
            return None
        match_rows = self._query(
            "SELECT result, released_by_user_id, notes, created_at FROM"
            " supplier_invoice_matches WHERE supplier_invoice_id=? ORDER BY created_at",
            (invoice_id,))
        releasers = {mr["released_by_user_id"]: mr["released_by_user_id"]
                     for mr in match_rows if mr.get("released_by_user_id")}
        named = self._with_actor_names([{"actor_user_id": user} for user in releasers])
        releasers = {item["actor_user_id"]: item["actor_name"] for item in named}
        matches = [InvoiceMatchDTO(
            result=mr["result"], released_by_user_id=mr["released_by_user_id"],
            notes=mr["notes"] or "", created_at=mr["created_at"],
            released_by_name=releasers.get(mr["released_by_user_id"], ""))
            for mr in match_rows]
        line_rows = self._query(
            "SELECT id,product_id,invoiced_quantity,unit_price,tax,"
            " purchase_order_line_id,direct_purchase_line_id,receipt_line_id"
            " FROM supplier_invoice_lines WHERE supplier_invoice_id=? ORDER BY id",
            (invoice_id,))
        names = product_labels(self._conn, (lr["product_id"] for lr in line_rows))
        lines = [InvoiceLineDTO(
            id=lr["id"], product_id=lr["product_id"], invoiced_quantity=lr["invoiced_quantity"],
            unit_price=lr["unit_price"], tax=lr["tax"],
            purchase_order_line_id=lr["purchase_order_line_id"],
            direct_purchase_line_id=lr["direct_purchase_line_id"],
            receipt_line_id=lr["receipt_line_id"],
            product_name=names.get(str(lr["product_id"]), UNKNOWN_PRODUCT)) for lr in line_rows]
        document_type = "PURCHASE_ORDER" if row.get("purchase_order_id") else "DIRECT_PURCHASE"
        document_id = row.get("purchase_order_id") or row.get("direct_purchase_id")
        comparison = self.billable_lines(document_type, document_id) if document_id else []
        return InvoiceDetailDTO(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], supplier_name=self._supplier_name(row["supplier_id"]),
            invoice_number=row["invoice_number"], subtotal=row["subtotal"],
            tax_total=row["tax_total"], total=row["total"], currency_code=row["currency_code"],
            status=row["status"], captured_by_user_id=row["captured_by_user_id"],
            created_at=row["created_at"], purchase_order_id=row["purchase_order_id"],
            direct_purchase_id=row["direct_purchase_id"], match_result=row["match_result"],
            matched_by_user_id=row["matched_by_user_id"],
            released_by_user_id=row["released_by_user_id"], operation_id=row["operation_id"],
            lines=lines, matches=matches, comparison=comparison,
            payable=self._payable(invoice_id),
            paid_in_cash=bool(row.get("direct_purchase_id")) and self._scalar(
                "SELECT payment_condition FROM direct_purchases WHERE id=?",
                (row.get("direct_purchase_id"),), default="") == "IMMEDIATE_PAYMENT")

    def _payable(self, invoice_id: str) -> dict | None:
        """La CxP que Finanzas creó para esta factura (lectura, no escritura:
        Compras no toca las tablas de Finanzas)."""
        return self._query_one(
            "SELECT d.document_number, p.original_amount, p.outstanding_amount,"
            " p.due_date, p.status FROM payables p"
            " JOIN financial_documents d ON d.id=p.financial_document_id"
            " WHERE d.source_module='procurement' AND d.source_document_id=?",
            (invoice_id,))


class ReceiptReadService(_Base):
    def list(self, *, branch_id: str | None = None, warehouse_id: str | None = None,
             limit=100) -> list[ReceiptRowDTO]:
        """Sin sucursal/almacén = todas (las compras son globales). La sesión
        real no trae almacén: filtrar por él dejaba la lista siempre vacía."""
        clauses, params = [], []
        if branch_id:
            clauses.append("g.branch_id=?")
            params.append(branch_id)
        if warehouse_id:
            clauses.append("g.warehouse_id=?")
            params.append(warehouse_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._query(
            "SELECT g.id,g.document_number,g.supplier_id,g.status,g.created_at,"
            " COALESCE(SUM(CAST(l.received_quantity AS NUMERIC)),0) received,"
            " COALESCE(SUM(CAST(l.accepted_quantity AS NUMERIC)),0) accepted,"
            " COALESCE(SUM(CAST(l.rejected_quantity AS NUMERIC)),0) rejected,"
            " (SELECT COUNT(*) FROM receipt_discrepancies d WHERE d.goods_receipt_id=g.id) differences"
            " FROM goods_receipts g"
            " LEFT JOIN goods_receipt_lines l ON l.goods_receipt_id=g.id"
            f"{where} GROUP BY g.id"
            " ORDER BY g.created_at DESC LIMIT ?", (*params, limit))
        result = []
        for row in rows:
            supplier = self._query_one("SELECT legal_name FROM supplier_master WHERE id=?",
                                       (row["supplier_id"],))
            supplier_name = supplier["legal_name"] if supplier else "Proveedor no disponible"
            result.append(ReceiptRowDTO(
                id=row["id"], document_number=row["document_number"],
                supplier_id=row["supplier_id"], supplier_name=supplier_name,
                status=row["status"], created_at=row["created_at"], received=row["received"],
                accepted=row["accepted"], rejected=row["rejected"],
                differences=row["differences"]))
        return result

    def detail(self, receipt_id: str) -> ReceiptDetailDTO | None:
        row = self._query_one("SELECT * FROM goods_receipts WHERE id=?", (receipt_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT id,product_id,ordered_quantity,received_quantity,accepted_quantity,"
            " rejected_quantity,lot,expiration,temperature FROM goods_receipt_lines"
            " WHERE goods_receipt_id=? ORDER BY id", (receipt_id,))
        lines = [GoodsReceiptLineDTO(
            id=lr["id"], product_id=lr["product_id"], ordered_quantity=lr["ordered_quantity"],
            received_quantity=lr["received_quantity"], accepted_quantity=lr["accepted_quantity"],
            rejected_quantity=lr["rejected_quantity"], lot=lr["lot"],
            expiration=lr["expiration"], temperature=lr["temperature"]) for lr in line_rows]
        difference_rows = self._query(
            "SELECT discrepancy_type,expected,actual,reason FROM receipt_discrepancies"
            " WHERE goods_receipt_id=? ORDER BY id", (receipt_id,))
        differences = [ReceiptDiscrepancyDTO(
            discrepancy_type=dr["discrepancy_type"], expected=dr["expected"],
            actual=dr["actual"], reason=dr["reason"] or "") for dr in difference_rows]
        invoices = self._query(
            "SELECT id,document_number,invoice_number,status,match_result,total"
            " FROM supplier_invoices WHERE purchase_order_id=? OR direct_purchase_id=?",
            (row.get("purchase_order_id"), row.get("direct_purchase_id")))
        return ReceiptDetailDTO(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], branch_id=row["branch_id"],
            warehouse_id=row["warehouse_id"], status=row["status"],
            created_at=row["created_at"], purchase_order_id=row["purchase_order_id"],
            direct_purchase_id=row["direct_purchase_id"],
            received_by_user_id=row["received_by_user_id"], operation_id=row["operation_id"],
            lines=lines, differences=differences, invoices=invoices,
            source_document_number=str(self._scalar(
                "SELECT document_number FROM purchase_orders WHERE id=?"
                " UNION ALL SELECT document_number FROM direct_purchases WHERE id=?",
                (row.get("purchase_order_id") or "", row.get("direct_purchase_id") or ""),
                default="")))


def _where(status_cols: tuple[str, ...], status, search: str,
           search_cols: tuple[str, ...], branch_id=None, start_date=None,
           end_date=None, branch_clause="branch_id = ?") -> tuple[str, list]:
    clauses, params = [], []
    if status:
        clauses.append(f"{status_cols[0]} = ?")
        params.append(status)
    if search and search.strip():
        like = f"%{search.strip()}%"
        ors = " OR ".join(f"{c} LIKE ?" for c in search_cols)
        clauses.append(f"({ors})")
        params.extend([like] * len(search_cols))
    if branch_id:
        clauses.append(branch_clause)
        params.extend([branch_id] * branch_clause.count("?"))
    # `created_at` está en UTC y el periodo en fecha LOCAL: comparar el texto
    # sacaba de la lista todo lo capturado después de las 18:00 (México) hasta
    # el día siguiente. Se compara la fecha local del documento.
    if start_date:
        clauses.append("date(created_at,'localtime') >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date(created_at,'localtime') <= ?")
        params.append(end_date)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
