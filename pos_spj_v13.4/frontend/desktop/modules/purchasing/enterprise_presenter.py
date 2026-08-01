"""EnterprisePurchasingPresenter — gateway between the enterprise procurement UI
(requisitions, orders, receiving, invoicing, analytics) and the backend.

Wires read/analytics services + use cases; never touches SQL/connections. Maps
results to (ok, message, data) tuples and produces display-ready view models.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.logistics.authorization import LogisticsPermissions
from frontend.desktop.modules.purchasing.enterprise_view_models import (
    PurchasingCapabilities, TableViewModel,
    invoice_status_es,
    match_result_es,
    money,
    order_status_es,
    requisition_status_es,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import SearchOption

logger = logging.getLogger("spj.purchasing.enterprise_presenter")

_PAGE_SIZE = 50


class EnterprisePurchasingPresenter:
    def __init__(self, *, connection_provider, read_services: dict, analytics,
                 use_cases: dict, session_context=None, event_dispatcher=None,
                 logistics_reads=None, warehouse_directory=None, history_reads=None,
                 origin_workspace=None) -> None:
        self._conn = connection_provider
        self._reads = read_services
        self._analytics = analytics
        self._use_cases = use_cases
        self._session = session_context
        self._dispatch = event_dispatcher
        self._logistics = logistics_reads
        self._warehouse_directory = warehouse_directory
        self._history = history_reads
        self._origin_workspace = origin_workspace
        self._supplier_directory = read_services.get("suppliers")
        self._period_start = None
        self._period_end = None
        self._invoice_sources = {}

    # session -----------------------------------------------------------------
    def _actor(self) -> str:
        user_id = getattr(self._session, "user_id", None)
        if not user_id:
            raise PermissionError("Se requiere una sesión autenticada de Compras")
        return str(user_id)

    def default_branch(self) -> str:
        branch_id = (getattr(self._session, "active_branch_id", None)
                     or getattr(self._session, "branch_id", None))
        if not branch_id:
            raise PermissionError("La sesión no tiene una sucursal activa")
        return str(branch_id)

    def default_warehouse(self) -> str:
        warehouse_id = (getattr(self._session, "active_warehouse_id", None)
                        or getattr(self._session, "warehouse_id", None))
        if not warehouse_id:
            raise PermissionError("La sesión no tiene un almacén activo")
        return str(warehouse_id)

    def selected_warehouse(self) -> str | None:
        """Return the explicit warehouse selection without inventing a default."""
        warehouse_id = (getattr(self._session, "active_warehouse_id", None)
                        or getattr(self._session, "warehouse_id", None))
        value = str(warehouse_id or "").strip()
        return value or None

    def warehouse_options(self) -> list[tuple[str, str]]:
        if self._warehouse_directory is None:
            return []
        return self._warehouse_directory.active_for_branch(self.default_branch())

    def select_warehouse(self, warehouse_id: str) -> None:
        options = dict(self.warehouse_options())
        if warehouse_id not in options:
            raise PermissionError("El almacén no pertenece a la sucursal activa")
        setter = getattr(self._session, "set_warehouse", None)
        if not callable(setter):
            raise PermissionError("La sesión no admite contexto de almacén")
        setter(warehouse_id, options[warehouse_id])

    def session_summary(self) -> dict[str, str | bool]:
        return {
            "user": str(getattr(self._session, "display_name", None)
                        or getattr(self._session, "nombre_completo", None)
                        or getattr(self._session, "username", None)
                        or getattr(self._session, "usuario", None) or "Sesión activa"),
            "branch": self.default_branch(),
            "warehouse": self.selected_warehouse() or "Sin almacén seleccionado",
            "warehouse_selected": bool(self.selected_warehouse()),
        }

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> PurchasingCapabilities:
        """Resolve UI visibility from the same permission constants as use cases."""
        allowed = self.can
        return PurchasingCapabilities(
            module_view=allowed(PurchasePermissions.VIEW),
            requisition_view=allowed(PurchasePermissions.REQUISITION_VIEW),
            requisition_create=allowed(PurchasePermissions.REQUISITION_CREATE),
            requisition_submit=allowed(PurchasePermissions.REQUISITION_SUBMIT),
            requisition_approve=allowed(PurchasePermissions.REQUISITION_APPROVE),
            requisition_reject=allowed(PurchasePermissions.REQUISITION_REJECT),
            rfq_create=allowed(PurchasePermissions.RFQ_CREATE),
            order_view=allowed(PurchasePermissions.ORDER_VIEW),
            order_create=allowed(PurchasePermissions.ORDER_CREATE),
            order_approve=allowed(PurchasePermissions.ORDER_APPROVE),
            order_send=allowed(PurchasePermissions.ORDER_SEND),
            order_change=allowed(PurchasePermissions.ORDER_CHANGE_APPROVED),
            receipt_view=allowed(PurchasePermissions.RECEIPT_VIEW),
            receipt_complete=allowed(PurchasePermissions.RECEIPT_COMPLETE),
            origin_view=allowed(LogisticsPermissions.SHIPMENT_VIEW),
            origin_create=allowed(LogisticsPermissions.SHIPMENT_CREATE),
            origin_seal=allowed(LogisticsPermissions.CONTAINER_SEAL),
            origin_dispatch=allowed(LogisticsPermissions.SHIPMENT_DISPATCH),
            origin_override=allowed(LogisticsPermissions.SHIPMENT_OVERRIDE),
            invoice_view=allowed(PurchasePermissions.INVOICE_VIEW),
            invoice_capture=allowed(PurchasePermissions.INVOICE_CAPTURE),
            invoice_match=allowed(PurchasePermissions.INVOICE_MATCH),
            invoice_release_variance=allowed(PurchasePermissions.INVOICE_RELEASE_VARIANCE),
            direct_view=allowed(PurchasePermissions.DIRECT_VIEW),
            direct_create=allowed(PurchasePermissions.DIRECT_CREATE),
            direct_authorize=allowed(PurchasePermissions.OVERRIDE_FINANCIAL_LIMIT),
            direct_confirm=allowed(PurchasePermissions.DIRECT_CONFIRM),
            direct_reverse=allowed(PurchasePermissions.DIRECT_REVERSE),
            view_costs=allowed(PurchasePermissions.VIEW_COSTS),
            view_analytics=allowed(PurchasePermissions.VIEW_ANALYTICS),
        )

    def navigation_badges(self, kpis=None) -> dict[str, int]:
        """Return display-ready pending counters; the shell performs no counting."""
        snapshot = kpis or self.analytics_kpis()
        return {
            "requisitions": int(snapshot.open_requisitions),
            "orders": int(snapshot.pending_order_approvals),
            "direct_purchase": int(snapshot.direct_purchases_today),
            "invoices": int(snapshot.invoices_with_differences),
        }

    def set_period(self, start_date: str, end_date: str) -> None:
        if start_date > end_date:
            raise ValueError("El periodo inicial no puede ser posterior al final")
        self._period_start, self._period_end = start_date, end_date

    def _scope(self) -> dict:
        return {"branch_id": self.default_branch(), "start_date": self._period_start,
                "end_date": self._period_end}

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
        rows = svc.list(status=status, search=search, limit=_PAGE_SIZE, offset=offset,
                        **self._scope())
        total = svc.count(status=status, search=search, **self._scope())
        data, ids = [], []
        for r in rows:
            data.append([r["document_number"], r["branch_id"], r["purchase_type"],
                         r["priority"], requisition_status_es(r["status"]),
                         (r["created_at"] or "")[:10]])
            ids.append(r["id"])
        return TableViewModel(data, ids, total=int(total))

    def requisition_detail(self, requisition_id: str):
        return self._reads["requisitions"].detail(requisition_id)

    def supplier_options(self, query: str):
        if self._supplier_directory is None or not query.strip():
            return []
        from frontend.desktop.modules.purchasing.direct_purchase_view_models import SearchOption
        return [SearchOption(id=row["id"], label=row["name"], subtitle=row.get("code") or "")
                for row in self._supplier_directory.search(query)]

    def create_rfq_from_requisition(self, requisition_id: str,
                                    supplier_ids: list[str]) -> tuple[bool, str, dict]:
        return self._run("rfq_create", actor_user_id=self._actor(),
                         requisition_id=requisition_id, supplier_ids=supplier_ids)

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
        rows = svc.list(status=status, search=search, limit=_PAGE_SIZE, offset=offset,
                        **self._scope())
        total = svc.count(status=status, search=search, **self._scope())
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
        rows = svc.list(status=status, search=search, limit=_PAGE_SIZE, offset=offset,
                        **self._scope())
        total = svc.count(status=status, search=search, **self._scope())
        data, ids = [], []
        for r in rows:
            data.append([r["document_number"], (r["supplier_id"] or "")[:8],
                         r["invoice_number"], money(r["total"]),
                         invoice_status_es(r["status"]), match_result_es(r["match_result"]),
                         (r["created_at"] or "")[:10]])
            ids.append(r["id"])
        return TableViewModel(data, ids, total=int(total))

    def invoice_detail(self, invoice_id: str):
        return self._reads["invoices"].detail(invoice_id)

    def invoice_document_options(self, query: str):
        rows = self._reads["invoices"].billable_documents(
            branch_id=self.default_branch(), search=query)
        for row in rows: self._invoice_sources[row["id"]] = row
        return [SearchOption(row["id"], row["document_number"],
                             f"{row['supplier_name']} · {row['document_type']}") for row in rows]

    def invoice_document_profile(self, document_id: str):
        row = dict(self._invoice_sources.get(document_id, {}))
        if row:
            row["lines"] = self._reads["invoices"].billable_lines(
                row["document_type"], document_id)
        return row

    def capture_invoice(self, **fields) -> tuple[bool, str, dict]:
        return self._run("inv_capture", actor_user_id=self._actor(), **fields)

    def match_invoice(self, invoice_id: str) -> tuple[bool, str, dict]:
        return self._run("inv_match", actor_user_id=self._actor(), invoice_id=invoice_id)

    def release_variance(self, invoice_id: str, *, reason) -> tuple[bool, str, dict]:
        return self._run("inv_release", releaser_user_id=self._actor(),
                         invoice_id=invoice_id, reason=reason)

    def receipts(self):
        return self._reads["receipts"].list(
            branch_id=self.default_branch(), warehouse_id=self.default_warehouse())

    def receipt_detail(self, receipt_id):
        return self._reads["receipts"].detail(receipt_id)

    def related_shipments(self) -> list[dict]:
        if self._logistics is None:
            return []
        return self._logistics.related_to_destination(
            branch_id=self.default_branch(), warehouse_id=self.default_warehouse())

    # ── origin purchase workspace ────────────────────────────────────────────
    def origin_documents(self, search="") -> list[dict]:
        if self._origin_workspace is None:
            return []
        return self._origin_workspace.documents(
            branch_id=self.default_branch(), warehouse_id=self.default_warehouse(),
            search=search)

    def origin_create_shipment(self, document: dict) -> tuple[bool, str, dict]:
        if self._origin_workspace is None:
            return False, "Logística no está configurada", {}
        try:
            detail = self._origin_workspace.create_shipment(
                actor_user_id=self._actor(), branch_id=self.default_branch(),
                warehouse_id=self.default_warehouse(), document=document)
            return True, "Embarque disponible para carga", detail
        except Exception as exc:
            logger.exception("origin shipment create failed")
            return False, str(exc), {}

    def origin_workspace(self, shipment_id: str) -> dict | None:
        return self._origin_workspace.open(shipment_id) if self._origin_workspace else None

    def origin_mobile_handoff(self, shipment_id: str) -> tuple[bool, str, dict]:
        try:
            handoff = self._origin_workspace.mobile_handoff(shipment_id)
            return True, "Sesión móvil contextualizada; el operador debe autenticarse.", handoff
        except Exception as exc:
            return False, str(exc), {}

    def origin_seal_root(self, shipment_id: str, node_id: str, seal_code: str):
        try:
            detail = self._origin_workspace.seal_root(
                actor_user_id=self._actor(), shipment_id=shipment_id,
                node_id=node_id, seal_code=seal_code)
            return True, "Contenedor sellado", detail
        except Exception as exc:
            return False, str(exc), {}

    def origin_dispatch(self, shipment_id: str):
        try:
            detail = self._origin_workspace.dispatch(
                actor_user_id=self._actor(), shipment_id=shipment_id)
            return True, "Embarque despachado", detail
        except Exception as exc:
            return False, str(exc), {}

    def origin_authorize_variance(self, shipment_id: str, source_line_id: str,
                                  reason: str):
        try:
            detail = self._origin_workspace.authorize_variance(
                actor_user_id=self._actor(), shipment_id=shipment_id,
                source_line_id=source_line_id, reason=reason)
            return True, "Variación autorizada y auditada", detail
        except Exception as exc:
            return False, str(exc), {}

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

    def analytics_alerts(self):
        return self._analytics.alerts()
