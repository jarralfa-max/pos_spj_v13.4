"""Read-only query services for suppliers. Paginated, no N+1, bank data masked.

Financial/purchase summaries read the existing finance/purchase tables and
tolerate their absence (return zeros) so the supplier context stays decoupled.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.application.suppliers.queries.supplier_search_query_service import (
    EmptySupplierReason,
    SupplierDirectorySearchQueryService,
    SupplierSearchQuery,
)
from backend.application.suppliers.dto.supplier_dtos import (
    SupplierDashboardDTO,
    SupplierRiskDTO,
)


def _mask_clabe(clabe: str | None) -> str:
    digits = "".join(ch for ch in (clabe or "") if ch.isdigit())
    return ("•" * max(0, len(digits) - 4)) + digits[-4:] if digits else ""


class _Base:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self._conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _scalar(self, sql: str, params: tuple = (), default: Any = 0) -> Any:
        try:
            row = self._conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError:
            return default
        return row[0] if row and row[0] is not None else default


class SearchSuppliersQueryService(_Base):
    """Búsqueda del módulo de Proveedores — delega en el contrato único.

    Tenía su propio SQL, distinto del de Compras. Ahora no tiene ninguno: la
    consulta la construye `SupplierDirectorySearchQueryService`, el mismo
    constructor que usa Compras, con la única diferencia de que aquí NO hay
    preset — este módulo existe para ver también borradores, pendientes de
    aprobación, suspendidos y dados de baja.

    De paso se corrige un fallo que traía: comparaba `normalized_name` contra el
    texto en crudo (`LIKE '%carnes del%'`), pero el maestro lo guarda sin
    espacios ni acentos (`carnesdelnortesa`), así que esa rama **no acertaba
    nunca** en cuanto el término tenía un espacio o un punto. Sólo funcionaba
    por `legal_name`.

    Sigue devolviendo diccionarios porque el presentador y sus pruebas los
    consumen así; es la misma consulta por dentro, no una segunda ruta.
    """

    def __init__(self, connection: Any) -> None:
        super().__init__(connection)
        self._search = SupplierDirectorySearchQueryService(connection)

    def search(self, *, query: str = "", status: str | None = None,
               category: str | None = None, risk_level: str | None = None,
               rating: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        tamano = max(int(limit), 1)
        encontrados = self._search.search(SupplierSearchQuery(
            text=query or None, status=status, category=category,
            risk_level=risk_level, rating=rating,
            page=(int(offset) // tamano) + 1, page_size=tamano))
        return [{"id": s.supplier_id, "supplier_code": s.supplier_code,
                 "legal_name": s.legal_name, "trade_name": s.trade_name,
                 "tax_identifier": s.tax_identifier, "status": s.status,
                 "rating_grade": s.rating_grade, "risk_level": s.risk_level,
                 "purchasing_blocked": s.purchasing_blocked}
                for s in encontrados]

    def count(self, *, query: str = "", status: str | None = None) -> int:
        return self._search.count(
            SupplierSearchQuery(text=query or None, status=status))

    def explain_empty(self, *, query: str = "", status: str | None = None
                      ) -> EmptySupplierReason | None:
        """Por qué el listado salió vacío. Antes la pantalla no podía
        distinguir "no hay proveedores" de "ninguno coincide"."""
        return self._search.explain_empty(
            SupplierSearchQuery(text=query or None, status=status))


class SupplierDetailQueryService(_Base):
    def get_header(self, supplier_id: str) -> dict | None:
        rows = self._query(
            "SELECT id, supplier_code, legal_name, trade_name, tax_identifier, status,"
            " rating_grade, risk_level, preferred_currency FROM supplier_master WHERE id=?",
            (supplier_id,))
        if not rows:
            return None
        header = rows[0]
        header["active_blocks"] = [b["block_type"] for b in self._query(
            "SELECT block_type FROM supplier_blocks WHERE supplier_id=? AND active=1",
            (supplier_id,))]
        header["counts"] = {
            "contacts": int(self._scalar("SELECT COUNT(*) FROM supplier_contacts WHERE supplier_id=?", (supplier_id,))),
            "addresses": int(self._scalar("SELECT COUNT(*) FROM supplier_addresses WHERE supplier_id=?", (supplier_id,))),
            "bank_accounts": int(self._scalar("SELECT COUNT(*) FROM supplier_bank_accounts WHERE supplier_id=?", (supplier_id,))),
            "products": int(self._scalar("SELECT COUNT(*) FROM supplier_products WHERE supplier_id=?", (supplier_id,))),
            "documents": int(self._scalar("SELECT COUNT(*) FROM supplier_documents WHERE supplier_id=?", (supplier_id,))),
        }
        return header

    def contacts(self, supplier_id: str) -> list[dict]:
        return self._query(
            "SELECT id, name, contact_type, role, phone_e164, whatsapp_e164, email,"
            " is_primary, active"
            " FROM supplier_contacts WHERE supplier_id=? ORDER BY is_primary DESC", (supplier_id,))

    def commercial_terms(self, supplier_id: str) -> dict | None:
        """Condiciones comerciales vigentes.

        NO existía: `UpdateSupplierCommercialTermsUseCase` guardaba y la pestaña
        "Condiciones" de la ficha mostraba un texto FIJO ("Edita las condiciones
        con el botón inferior"). Se capturaban y no se volvían a ver — el mismo
        patrón que tenían los domicilios.
        """
        rows = self._query(
            "SELECT credit_days, credit_limit, currency_code, is_credit,"
            " preferred_payment_method, advance_required, advance_percentage,"
            " lead_time_days, receiving_window_start, receiving_window_end"
            " FROM supplier_commercial_terms WHERE supplier_id=?", (supplier_id,))
        return rows[0] if rows else None

    def addresses(self, supplier_id: str) -> list[dict]:
        """Direcciones del proveedor.

        NO existía, y su ausencia era asimétrica: el encabezado ya las CONTABA
        (`COUNT(*) FROM supplier_addresses`) y el repositorio sabe leerlas
        (`SupplierAddressRepository.list_by_supplier`), pero el servicio que
        alimenta la ficha no las exponía. El efecto real es que una dirección se
        podía guardar —`AddSupplierAddressUseCase` funciona desde el principio—
        y no se podía volver a ver NUNCA.

        `country_code` y `validation_state` se proyectan aunque la tabla de la
        ficha no los pinte hoy: son parte del domicilio y pedirlos después
        obligaría a tocar otra vez esta consulta.
        """
        return self._query(
            "SELECT id, address_type, line, city, state, postal_code, country_code,"
            " validation_state FROM supplier_addresses WHERE supplier_id=?"
            " ORDER BY address_type", (supplier_id,))

    def bank_accounts(self, supplier_id: str, *, can_view_full: bool = False) -> list[dict]:
        rows = self._query(
            "SELECT id, bank_name, account_holder, currency_code, account_type, clabe,"
            " account_number, status, verified_at FROM supplier_bank_accounts"
            " WHERE supplier_id=?", (supplier_id,))
        for r in rows:
            if not can_view_full:
                r["clabe"] = _mask_clabe(r["clabe"])
                acct = r.get("account_number") or ""
                r["account_number"] = ("•" * max(0, len(acct) - 4)) + acct[-4:] if acct else ""
        return rows

    def documents(self, supplier_id: str) -> list[dict]:
        return self._query(
            "SELECT id, document_type, status, issued_at, expires_at, verified_at"
            " FROM supplier_documents WHERE supplier_id=? ORDER BY expires_at", (supplier_id,))

    def products(self, supplier_id: str) -> list[dict]:
        return self._query(
            "SELECT id, product_id, supplier_sku, purchase_unit, current_cost, currency_code,"
            " preferred FROM supplier_products WHERE supplier_id=? AND active=1", (supplier_id,))


class SupplierDashboardQueryService(_Base):
    def overview(self, *, expiring_days: int = 30) -> SupplierDashboardDTO:
        active = int(self._scalar("SELECT COUNT(*) FROM supplier_master WHERE status='ACTIVE'"))
        pending = int(self._scalar("SELECT COUNT(*) FROM supplier_master WHERE status='PENDING_APPROVAL'"))
        blocked = int(self._scalar("SELECT COUNT(*) FROM supplier_master WHERE status='BLOCKED'"))
        expiring = int(self._scalar(
            "SELECT COUNT(*) FROM supplier_documents WHERE status IN ('EXPIRING','EXPIRED')"))
        # payables come from the finance context; tolerate their absence
        payable = self._scalar(
            "SELECT COALESCE(SUM(CAST(outstanding_amount AS NUMERIC)),0) FROM payables"
            " WHERE status NOT IN ('SETTLED','WRITTEN_OFF','CANCELLED')", default=0)
        overdue = self._scalar(
            "SELECT COALESCE(SUM(CAST(outstanding_amount AS NUMERIC)),0) FROM payables"
            " WHERE due_date < date('now') AND status NOT IN ('SETTLED','WRITTEN_OFF','CANCELLED')",
            default=0)
        return SupplierDashboardDTO(
            active_suppliers=active, pending_approval=pending, blocked=blocked,
            payable_balance=f"{float(payable):.2f}", overdue_balance=f"{float(overdue):.2f}",
            documents_expiring=expiring)


class SupplierFinancialSummaryQueryService(_Base):
    def summary(self, supplier_id: str) -> dict:
        balance = self._scalar(
            "SELECT COALESCE(SUM(CAST(outstanding_amount AS NUMERIC)),0) FROM payables"
            " WHERE supplier_id=? AND status NOT IN ('SETTLED','WRITTEN_OFF','CANCELLED')",
            (supplier_id,), default=0)
        overdue = self._scalar(
            "SELECT COALESCE(SUM(CAST(outstanding_amount AS NUMERIC)),0) FROM payables"
            " WHERE supplier_id=? AND due_date < date('now')"
            " AND status NOT IN ('SETTLED','WRITTEN_OFF','CANCELLED')", (supplier_id,), default=0)
        open_docs = int(self._scalar(
            "SELECT COUNT(*) FROM payables WHERE supplier_id=? AND status NOT IN"
            " ('SETTLED','WRITTEN_OFF','CANCELLED')", (supplier_id,), default=0))
        return {"balance": f"{float(balance):.2f}", "overdue": f"{float(overdue):.2f}",
                "open_documents": open_docs}


class SupplierPerformanceQueryService(_Base):
    def performance(self, supplier_id: str) -> dict:
        row = self._query(
            "SELECT score, rating_grade, period FROM supplier_evaluations"
            " WHERE supplier_id=? ORDER BY period DESC LIMIT 1", (supplier_id,))
        latest = row[0] if row else {"score": None, "rating_grade": None, "period": None}
        avg = self._scalar(
            "SELECT AVG(score) FROM supplier_evaluations WHERE supplier_id=?",
            (supplier_id,), default=None)
        return {"latest_score": latest["score"], "latest_rating": latest["rating_grade"],
                "latest_period": latest["period"],
                "average_score": round(float(avg), 1) if avg is not None else None}


class SupplierPurchaseHistoryQueryService(_Base):
    def history(self, supplier_id: str, *, limit: int = 50) -> list[dict]:
        try:
            return self._query(
                "SELECT c.id, c.fecha, c.total FROM compras c WHERE c.proveedor_id=?"
                " ORDER BY c.fecha DESC LIMIT ?", (supplier_id, limit))
        except sqlite3.OperationalError:
            return []


class SupplierRiskQueryService(_Base):
    """Computes supplier risk with explicit causes (never just a color)."""

    def assess(self, supplier_id: str) -> SupplierRiskDTO:
        causes: list[str] = []
        weight = 0

        expired = int(self._scalar(
            "SELECT COUNT(*) FROM supplier_documents WHERE supplier_id=? AND status='EXPIRED'",
            (supplier_id,)))
        if expired:
            causes.append(f"{expired} documento(s) vencido(s)"); weight += 2 * expired

        unverified = int(self._scalar(
            "SELECT COUNT(*) FROM supplier_bank_accounts WHERE supplier_id=?"
            " AND status!='VERIFIED'", (supplier_id,)))
        if unverified:
            causes.append("Cuenta bancaria sin verificar"); weight += 2

        active_blocks = int(self._scalar(
            "SELECT COUNT(*) FROM supplier_blocks WHERE supplier_id=? AND active=1",
            (supplier_id,)))
        if active_blocks:
            causes.append(f"{active_blocks} bloqueo(s) activo(s)"); weight += 2 * active_blocks

        rating = self._scalar(
            "SELECT rating_grade FROM supplier_master WHERE id=?", (supplier_id,), default=None)
        if rating in ("C", "D"):
            causes.append(f"Evaluación baja (rating {rating})")
            weight += 1 if rating == "C" else 3

        if weight >= 6:
            level = "CRITICAL"
        elif weight >= 4:
            level = "HIGH"
        elif weight >= 2:
            level = "MEDIUM"
        else:
            level = "LOW"
        return SupplierRiskDTO(supplier_id=supplier_id, level=level, causes=tuple(causes))
