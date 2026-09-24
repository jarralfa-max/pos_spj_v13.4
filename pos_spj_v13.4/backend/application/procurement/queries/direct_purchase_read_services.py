"""Read-only query services for the direct-purchase UI (paginated, no business
logic). The UI never issues SQL; it asks these services for display-ready rows."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.application.suppliers.queries.supplier_search_query_service import (
    EmptySupplierReason,
    SearchProcurementSuppliersQueryService,
    SupplierSearchQuery,
)
from backend.application.procurement.dto.direct_purchase_dtos import (
    DirectPurchaseDetailDTO,
    DirectPurchaseLineDTO,
    DirectPurchaseRowDTO,
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

    def _scalar(self, sql: str, params: tuple = (), default: Any = 0) -> Any:
        try:
            row = self._conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError:
            return default
        return row[0] if row and row[0] is not None else default


class DirectPurchaseReadService(_Base):
    def supplier_name(self, supplier_id: str) -> str:
        row = self._query_one("SELECT legal_name FROM supplier_master WHERE id=?", (supplier_id,))
        return str(row["legal_name"]) if row else "Proveedor no disponible"

    def count(self, *, status: str | None = None, search: str = "") -> int:
        where, params = self._where(status, search)
        return int(self._scalar(
            f"SELECT COUNT(*) FROM direct_purchases{where}", tuple(params), default=0))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0) -> list[DirectPurchaseRowDTO]:
        where, params = self._where(status, search)
        rows = self._query(
            "SELECT direct_purchases.id, document_number, supplier_id, branch_id, status, total,"
            " currency_code, payment_condition, direct_purchases.created_at,"
            " COALESCE(p.legal_name, '—') AS supplier_name FROM direct_purchases"
            " LEFT JOIN (SELECT id, legal_name FROM supplier_master) p ON p.id = direct_purchases.supplier_id"
            f"{where} ORDER BY direct_purchases.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset))
        return [DirectPurchaseRowDTO(
            id=r["id"], document_number=r["document_number"], supplier_id=r["supplier_id"],
            branch_id=r["branch_id"], status=r["status"], total=r["total"],
            currency_code=r["currency_code"], payment_condition=r["payment_condition"],
            created_at=r["created_at"], supplier_name=r["supplier_name"]) for r in rows]

    def get_detail(self, direct_purchase_id: str) -> DirectPurchaseDetailDTO | None:
        row = self._query_one("SELECT * FROM direct_purchases WHERE id=?",
                              (direct_purchase_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT product_id, description, quantity, unit_cost, discount, tax, line_total,"
            " purchase_unit, inventory_unit, conversion_factor"
            " FROM direct_purchase_lines WHERE direct_purchase_id=? ORDER BY id",
            (direct_purchase_id,))
        lines = [DirectPurchaseLineDTO(
            product_id=lr["product_id"], description=lr["description"] or "",
            quantity=lr["quantity"], unit_cost=lr["unit_cost"], discount=lr["discount"],
            tax=lr["tax"], line_total=lr["line_total"], purchase_unit=lr["purchase_unit"],
            inventory_unit=lr["inventory_unit"], conversion_factor=lr["conversion_factor"])
            for lr in line_rows]
        return DirectPurchaseDetailDTO(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], branch_id=row["branch_id"],
            warehouse_id=row["warehouse_id"], status=row["status"], mode=row["mode"],
            payment_condition=row["payment_condition"], currency_code=row["currency_code"],
            subtotal=row["subtotal"], tax_total=row["tax_total"], total=row["total"],
            authorization_reason=row["authorization_reason"] or "",
            authorized_by_user_id=row["authorized_by_user_id"],
            created_by_user_id=row["created_by_user_id"], lines=lines)

    def _where(self, status: str | None, search: str) -> tuple[str, list]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if search.strip():
            clauses.append("(document_number LIKE ? OR supplier_id LIKE ?)")
            like = f"%{search.strip()}%"
            params.extend([like, like])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params


class SupplierPickerQueryService(_Base):
    """Buscador de proveedores de Compras — sobre el MAESTRO CANÓNICO.

    LEÍA `proveedores`, la tabla heredada, mientras el módulo de Proveedores
    leía `supplier_master`. Los dos conjuntos eran DISJUNTOS y nada en
    producción escribía en la heredada: un proveedor dado de alta y aprobado hoy
    no se podía elegir al crear una compra. Es el corte SUP-6 que la migración
    119 dejó anunciado; la 263 copia los heredados al maestro conservando su id.

    No tiene SQL propio: delega en el contrato único
    (`SupplierSearchQuery`), igual que Compras hace con la búsqueda de
    productos. Aquí sólo se traduce el resultado a la forma de fila que los dos
    presentadores de Compras ya consumían, para no arrastrar el cambio hasta la
    pantalla.
    """

    def __init__(self, connection: Any) -> None:
        super().__init__(connection)
        self._search = SearchProcurementSuppliersQueryService(connection)

    def search(self, query: str, *, limit: int = 25) -> list[dict]:
        try:
            encontrados = self._search.search(
                SupplierSearchQuery(text=query, page_size=max(int(limit), 1)))
        except sqlite3.OperationalError:
            # Base sin el maestro (la 119 no corrió). Antes se degradaba a la
            # tabla heredada; ahora se devuelve vacío porque esa tabla ya no es
            # la fuente — y un selector vacío es menos dañino que uno que ofrece
            # proveedores que la puerta de guardado va a rechazar.
            return []
        return [
            {"id": s.supplier_id, "name": s.trade_name or s.legal_name,
             "code": s.supplier_code, "status": 1,
             # Los dos presentadores etiquetan el bloqueo con estas dos claves y
             # dan MENSAJES distintos ("Bloqueado financieramente" frente a
             # "Compras deshabilitadas"). El maestro no las guarda como columnas
             # sino como tipos de fila en `supplier_blocks`, así que se mapea
             # cada tipo a su clave: colapsarlas en una sola habría degradado el
             # mensaje sin que ninguna prueba lo notara.
             "bloqueado_financiero": 1 if s.payment_blocked else 0,
             "compras_habilitadas": 0 if s.purchasing_blocked else 1}
            for s in encontrados
        ]

    def explain_empty(self, query: str) -> EmptySupplierReason | None:
        """Por qué el selector no devolvió nada. Mismo trato que en Productos:
        "Sin resultados" no distingue un catálogo vacío de un término que no
        coincide, y son cosas que se arreglan de forma distinta."""
        try:
            return self._search.explain_empty(SupplierSearchQuery(text=query))
        except sqlite3.OperationalError:
            return None
