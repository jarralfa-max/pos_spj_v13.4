"""SupplierPresenter — the only gateway between the suppliers UI and the backend.

Receives already-wired query services and use cases. Never touches SQL,
connections or repositories; returns display-ready view models and runs use
cases, mapping SupplierResult to (ok, message) tuples for the pages.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid
from frontend.desktop.modules.finance.suppliers.supplier_view_models import (
    KpiVM,
    TableViewModel,
    category_es,
    money,
    risk_es,
    status_es,
)

logger = logging.getLogger("spj.suppliers.presenter")

_PAGE_SIZE = 50


class SupplierPresenter:
    def __init__(self, *, connection_provider, query_services: dict, use_cases: dict,
                 session_context=None) -> None:
        self._conn = connection_provider
        self._queries = query_services
        self._use_cases = use_cases
        self._session = session_context

    # helpers -----------------------------------------------------------------
    def _actor(self) -> str:
        user_id = getattr(self._session, "user_id", None)
        return str(user_id) if user_id else "desktop"

    def _can(self, permission_code: str) -> bool:
        perms = getattr(self._session, "permissions", None)
        return True if perms is None else permission_code in perms

    def _run(self, use_case_key: str, **kwargs) -> tuple[bool, str, dict]:
        try:
            result = self._use_cases[use_case_key].execute(
                self._conn(), actor_user_id=self._actor(), operation_id=new_uuid(), **kwargs)
            return bool(result.success), result.message, dict(result.data)
        except Exception:
            logger.exception("SupplierPresenter: unexpected error in %s", use_case_key)
            return False, "Error inesperado; revise el log.", {}

    # reads -------------------------------------------------------------------
    def overview_kpis(self) -> list[KpiVM]:
        d = self._queries["dashboard"].overview()
        return [
            KpiVM("Proveedores activos", str(d.active_suppliers), "primary"),
            KpiVM("Pendientes de aprobación", str(d.pending_approval), "warning"),
            KpiVM("Bloqueados", str(d.blocked), "danger"),
            KpiVM("Saldo por pagar", money(d.payable_balance), "primary"),
            KpiVM("Saldo vencido", money(d.overdue_balance), "danger"),
            KpiVM("Documentos por vencer", str(d.documents_expiring), "warning"),
        ]

    def suppliers(self, *, search: str = "", status: str | None = None,
                  category: str | None = None, risk_level: str | None = None,
                  rating: str | None = None, page: int = 0) -> TableViewModel:
        offset = max(0, page) * _PAGE_SIZE
        rows_data = self._queries["search"].search(
            query=search, status=status, category=category, risk_level=risk_level,
            rating=rating, limit=_PAGE_SIZE, offset=offset)
        total = self._queries["search"].count(query=search, status=status)
        rows, ids = [], []
        for r in rows_data:
            rows.append([
                r["supplier_code"], r["legal_name"], r["tax_identifier"] or "—",
                status_es(r["status"]), r["rating_grade"] or "—", risk_es(r["risk_level"]),
            ])
            ids.append(r["id"])
        return TableViewModel(rows, ids, total=int(total))

    def supplier_header(self, supplier_id: str) -> dict | None:
        header = self._queries["detail"].get_header(supplier_id)
        if header is None:
            return None
        header["status_label"] = status_es(header["status"])
        header["risk_label"] = risk_es(header["risk_level"])
        return header

    def contacts(self, supplier_id: str) -> TableViewModel:
        rows, ids = [], []
        for c in self._queries["detail"].contacts(supplier_id):
            rows.append([c["name"], c["contact_type"], c["role"] or "—",
                         c["phone_e164"] or "—", c["email"] or "—",
                         "Sí" if c["is_primary"] else "No"])
            ids.append(c["id"])
        return TableViewModel(rows, ids)

    def bank_accounts(self, supplier_id: str) -> TableViewModel:
        # Bank data is sensitive: masked by default, unmasked ONLY when the
        # session explicitly grants VIEW_BANK (dev's permissive default never
        # exposes account numbers).
        perms = getattr(self._session, "permissions", None)
        can_full = bool(perms) and "SUPPLIERS_VIEW_BANK" in perms
        rows, ids = [], []
        for b in self._queries["detail"].bank_accounts(supplier_id, can_view_full=can_full):
            rows.append([b["bank_name"], b["account_holder"], b["clabe"] or "—",
                         b["currency_code"], status_es(b["status"])])
            ids.append(b["id"])
        return TableViewModel(rows, ids)

    def documents(self, supplier_id: str) -> TableViewModel:
        rows, ids = [], []
        for d in self._queries["detail"].documents(supplier_id):
            rows.append([d["document_type"], status_es(d["status"]),
                         d["issued_at"] or "—", d["expires_at"] or "—"])
            ids.append(d["id"])
        return TableViewModel(rows, ids)

    def products(self, supplier_id: str) -> TableViewModel:
        rows, ids = [], []
        for p in self._queries["detail"].products(supplier_id):
            rows.append([p["product_id"][:8], p["supplier_sku"] or "—",
                         p["purchase_unit"] or "—", money(p["current_cost"]),
                         "Sí" if p["preferred"] else "No"])
            ids.append(p["id"])
        return TableViewModel(rows, ids)

    def risk(self, supplier_id: str) -> dict:
        dto = self._queries["risk"].assess(supplier_id)
        return {"level": dto.level, "label": risk_es(dto.level), "causes": list(dto.causes)}

    def category_label(self, code: str) -> str:
        return category_es(code)

    # actions -----------------------------------------------------------------
    def create_supplier(self, **fields) -> tuple[bool, str, dict]:
        return self._run("create", **fields)

    def submit_for_approval(self, supplier_id: str) -> tuple[bool, str, dict]:
        return self._run("submit", supplier_id=supplier_id)

    def approve(self, supplier_id: str) -> tuple[bool, str, dict]:
        return self._run("approve", supplier_id=supplier_id)

    def reject(self, supplier_id: str, reason: str) -> tuple[bool, str, dict]:
        return self._run("reject", supplier_id=supplier_id, reason=reason)

    def suspend(self, supplier_id: str, reason: str) -> tuple[bool, str, dict]:
        return self._run("suspend", supplier_id=supplier_id, reason=reason)

    def activate(self, supplier_id: str) -> tuple[bool, str, dict]:
        return self._run("activate", supplier_id=supplier_id)

    def block(self, supplier_id: str, *, block_type: str, reason: str) -> tuple[bool, str, dict]:
        return self._run("block", supplier_id=supplier_id, block_type=block_type, reason=reason)

    def unblock(self, supplier_id: str, *, block_type: str) -> tuple[bool, str, dict]:
        return self._run("unblock", supplier_id=supplier_id, block_type=block_type)

    def add_contact(self, **fields) -> tuple[bool, str, dict]:
        return self._run("add_contact", **fields)

    def add_bank_account(self, **fields) -> tuple[bool, str, dict]:
        return self._run("add_bank", **fields)

    def verify_bank_account(self, bank_account_id: str) -> tuple[bool, str, dict]:
        return self._run("verify_bank", bank_account_id=bank_account_id)

    def update_terms(self, **fields) -> tuple[bool, str, dict]:
        return self._run("update_terms", **fields)

    def evaluate(self, **fields) -> tuple[bool, str, dict]:
        return self._run("evaluate", **fields)
