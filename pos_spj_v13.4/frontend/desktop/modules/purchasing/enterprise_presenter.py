"""EnterprisePurchasingPresenter — gateway between the enterprise procurement UI
(requisitions, orders, receiving, invoicing, analytics) and the backend.

Wires read/analytics services + use cases; never touches SQL/connections. Maps
results to (ok, message, data) tuples and produces display-ready view models.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid
from frontend.desktop.modules.purchasing.enterprise_view_models import (
    TableViewModel,
    invoice_status_es,
    match_result_es,
    money,
    order_status_es,
    requisition_status_es,
)

logger = logging.getLogger("spj.purchasing.enterprise_presenter")

_PAGE_SIZE = 50


class EnterprisePurchasingPresenter:
    def __init__(self, *, connection_provider, read_services: dict, analytics,
                 use_cases: dict, session_context=None, event_dispatcher=None,
                 qr_reads=None, history_reads=None) -> None:
        self._conn = connection_provider
        self._reads = read_services
        self._analytics = analytics
        self._use_cases = use_cases
        self._session = session_context
        self._dispatch = event_dispatcher
        self._qr = qr_reads
        self._history = history_reads

    # session -----------------------------------------------------------------
    def _actor(self) -> str:
        user_id = getattr(self._session, "user_id", None)
        return str(user_id) if user_id else "desktop"

    def default_branch(self) -> str:
        return str(getattr(self._session, "branch_id", None) or "MAIN")

    def default_warehouse(self) -> str:
        return str(getattr(self._session, "warehouse_id", None) or self.default_branch())

    def _run(self, key: str, **kwargs) -> tuple[bool, str, dict]:
        try:
            result = self._use_cases[key].execute(self._conn(), operation_id=new_uuid(), **kwargs)
            data = dict(result.data)
            if result.entity_id is not None:
                data.setdefault("entity_id", result.entity_id)
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()   # post-commit: publish outbox → downstream
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, data
        except Exception:
            logger.exception("EnterprisePurchasingPresenter: error in %s", key)
            return False, "Error inesperado; revise el log.", {}

    # ── requisitions ─────────────────────────────────────────────────────────
    def requisitions(self, *, status=None, search="", page=0) -> TableViewModel:
        svc = self._reads["requisitions"]
        offset = max(0, page) * _PAGE_SIZE
        rows = svc.list(status=status, search=search, limit=_PAGE_SIZE, offset=offset)
        total = svc.count(status=status, search=search)
        data, ids = [], []
        for r in rows:
            data.append([r["document_number"], r["branch_id"], r["purchase_type"],
                         r["priority"], requisition_status_es(r["status"]),
                         (r["created_at"] or "")[:10]])
            ids.append(r["id"])
        return TableViewModel(data, ids, total=int(total))

    def create_requisition(self, **fields) -> tuple[bool, str, dict]:
        return self._run("req_create", actor_user_id=self._actor(), **fields)

    def submit_requisition(self, requisition_id: str) -> tuple[bool, str, dict]:
        return self._run("req_submit", actor_user_id=self._actor(),
                         requisition_id=requisition_id)

    def approve_requisition(self, requisition_id: str, *, approve=True,
                            reason="") -> tuple[bool, str, dict]:
        return self._run("req_approve", approver_user_id=self._actor(),
                         requisition_id=requisition_id, approve=approve, reason=reason)

    # ── orders ────────────────────────────────────────────────────────────────
    def orders(self, *, status=None, search="", page=0) -> TableViewModel:
        svc = self._reads["orders"]
        offset = max(0, page) * _PAGE_SIZE
        rows = svc.list(status=status, search=search, limit=_PAGE_SIZE, offset=offset)
        total = svc.count(status=status, search=search)
        data, ids = [], []
        for r in rows:
            data.append([r["document_number"], (r["supplier_id"] or "")[:8],
                         order_status_es(r["status"]), f"v{r['version']}",
                         money(r["total"]), (r["created_at"] or "")[:10]])
            ids.append(r["id"])
        return TableViewModel(data, ids, total=int(total))

    def order_detail(self, order_id: str):
        return self._reads["orders"].detail(order_id)

    def create_order(self, **fields) -> tuple[bool, str, dict]:
        return self._run("po_create", actor_user_id=self._actor(), **fields)

    def approve_order(self, order_id: str, *, reason="") -> tuple[bool, str, dict]:
        return self._run("po_approve", approver_user_id=self._actor(),
                         purchase_order_id=order_id, reason=reason)

    def send_order(self, order_id: str, *, acknowledge=False) -> tuple[bool, str, dict]:
        return self._run("po_send", actor_user_id=self._actor(),
                         purchase_order_id=order_id, acknowledge=acknowledge)

    def change_order(self, order_id: str, *, reason, line_changes=None) -> tuple[bool, str, dict]:
        return self._run("po_change", actor_user_id=self._actor(),
                         purchase_order_id=order_id, reason=reason,
                         line_changes=line_changes or [])

    def receive_order(self, order_id: str, *, receipt_lines,
                      has_over_receive_permission=False) -> tuple[bool, str, dict]:
        return self._run("po_receive", actor_user_id=self._actor(),
                         purchase_order_id=order_id, receipt_lines=receipt_lines,
                         has_over_receive_permission=has_over_receive_permission)

    # ── invoices ─────────────────────────────────────────────────────────────
    def invoices(self, *, status=None, search="", page=0) -> TableViewModel:
        svc = self._reads["invoices"]
        offset = max(0, page) * _PAGE_SIZE
        rows = svc.list(status=status, search=search, limit=_PAGE_SIZE, offset=offset)
        total = svc.count(status=status, search=search)
        data, ids = [], []
        for r in rows:
            data.append([r["document_number"], (r["supplier_id"] or "")[:8],
                         r["invoice_number"], money(r["total"]),
                         invoice_status_es(r["status"]), match_result_es(r["match_result"]),
                         (r["created_at"] or "")[:10]])
            ids.append(r["id"])
        return TableViewModel(data, ids, total=int(total))

    def capture_invoice(self, **fields) -> tuple[bool, str, dict]:
        return self._run("inv_capture", actor_user_id=self._actor(), **fields)

    def match_invoice(self, invoice_id: str) -> tuple[bool, str, dict]:
        return self._run("inv_match", actor_user_id=self._actor(), invoice_id=invoice_id)

    def release_variance(self, invoice_id: str, *, captured_by_user_id,
                         reason) -> tuple[bool, str, dict]:
        return self._run("inv_release", releaser_user_id=self._actor(),
                         invoice_id=invoice_id, captured_by_user_id=captured_by_user_id,
                         reason=reason)

    # ── QR container lifecycle ────────────────────────────────────────────────
    def qr_available(self) -> TableViewModel:
        rows = self._qr.available_containers() if self._qr else []
        data = [[r["code"], r["description"], r["status"]] for r in rows]
        return TableViewModel(data, [r["uuid_qr"] for r in rows], total=len(rows))

    def qr_pending(self) -> TableViewModel:
        rows = self._qr.pending_reception() if self._qr else []
        data = [[r["code"], r["supplier"], r["status"]] for r in rows]
        return TableViewModel(data, [r["uuid_qr"] for r in rows], total=len(rows))

    def qr_history(self, desde: str, hasta: str) -> TableViewModel:
        rows = self._qr.history(desde, hasta) if self._qr else []
        data = [[r["container"], r["supplier"], r["destination"], r["status"],
                 (r["received_at"] or "—")[:19]] for r in rows]
        return TableViewModel(data, [r["uuid_qr"] for r in rows], total=len(rows))

    def qr_search_suppliers(self, text: str) -> list[dict]:
        return self._qr.search_suppliers(text) if (self._qr and text.strip()) else []

    def qr_search_products(self, text: str) -> list[dict]:
        return self._qr.search_products(text) if (self._qr and text.strip()) else []

    def generate_qr_label(self, *, description: str) -> tuple[bool, str, dict]:
        return self._run("qr_register", actor_user_id=self._actor(),
                         description=description, origin_branch_id=self.default_branch())

    def assign_qr(self, *, uuid_qr: str, supplier_id: str, items: list,
                  payment_condition: str) -> tuple[bool, str, dict]:
        return self._run("qr_assign", actor_user_id=self._actor(), uuid_qr=uuid_qr,
                         supplier_id=supplier_id, items=items,
                         payment_condition=payment_condition,
                         origin_branch_id=self.default_branch())

    def complete_qr_reception(self, *, uuid_qr: str, items: list) -> tuple[bool, str, dict]:
        return self._run("qr_receive", actor_user_id=self._actor(), uuid_qr=uuid_qr,
                         items=items, branch_id=self.default_branch(),
                         warehouse_id=self.default_warehouse())

    # ── documental purchase history ───────────────────────────────────────────
    def purchase_history(self) -> TableViewModel:
        if self._history is None:
            return TableViewModel([], [], 0)
        rows = self._history.canonical_receipts(limit=100)
        data = [[r["document_number"], (r["supplier_id"] or "")[:8], r["status"],
                 (r["created_at"] or "")[:19]] for r in rows]
        return TableViewModel(data, [r["document_number"] for r in rows], total=len(rows))

    # ── analytics ─────────────────────────────────────────────────────────────
    def analytics_kpis(self):
        return self._analytics.kpis()

    def analytics_charts(self):
        return self._analytics.all_charts()
