"""EnterprisePurchasingPresenter — gateway between the enterprise procurement UI
(requisitions, orders, receiving, invoicing, analytics) and the backend.

Wires read/analytics services + use cases; never touches SQL/connections. Maps
results to (ok, message, data) tuples and produces display-ready view models.
"""

from __future__ import annotations

import logging

from backend.application.logistics.authorization import LogisticsPermissions
from backend.application.procurement.permissions import PurchasePermissions
from backend.shared.ids import new_uuid
from frontend.desktop.modules.purchasing.enterprise_view_models import (
    PurchasingCapabilities,
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
        self._origin = origin_workspace
        self._period_start = None
        self._period_end = None

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
        P = PurchasePermissions
        L = LogisticsPermissions
        return PurchasingCapabilities(
            module_view=self.can(P.VIEW),
            requisition_view=self.can(P.REQUISITION_VIEW),
            requisition_create=self.can(P.REQUISITION_CREATE),
            requisition_submit=self.can(P.REQUISITION_SUBMIT),
            requisition_approve=self.can(P.REQUISITION_APPROVE),
            requisition_reject=self.can(P.REQUISITION_REJECT),
            rfq_create=self.can(P.RFQ_CREATE),
            order_view=self.can(P.ORDER_VIEW),
            order_create=self.can(P.ORDER_CREATE),
            order_approve=self.can(P.ORDER_APPROVE),
            order_send=self.can(P.ORDER_SEND),
            order_change=self.can(P.ORDER_CHANGE_APPROVED),
            receipt_view=self.can(P.RECEIPT_VIEW),
            receipt_complete=self.can(P.RECEIPT_COMPLETE),
            origin_view=self.can(L.SHIPMENT_VIEW),
            origin_create=self.can(L.SHIPMENT_CREATE),
            origin_seal=self.can(L.CONTAINER_SEAL),
            origin_dispatch=self.can(L.SHIPMENT_DISPATCH),
            origin_override=self.can(L.SHIPMENT_OVERRIDE),
            invoice_view=self.can(P.INVOICE_VIEW),
            invoice_capture=self.can(P.INVOICE_CAPTURE),
            invoice_match=self.can(P.INVOICE_MATCH),
            invoice_release_variance=self.can(P.INVOICE_RELEASE_VARIANCE),
            direct_view=self.can(P.DIRECT_VIEW),
            direct_create=self.can(P.DIRECT_CREATE),
            direct_authorize=self.can(P.OVERRIDE_FINANCIAL_LIMIT),
            direct_confirm=self.can(P.DIRECT_CONFIRM),
            direct_reverse=self.can(P.DIRECT_REVERSE),
            view_costs=self.can(P.VIEW_COSTS),
            view_analytics=self.can(P.VIEW_ANALYTICS),
        )

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

    def create_requisition(self, **fields) -> tuple[bool, str, dict]:
        return self._run("req_create", actor_user_id=self._actor(), **fields)

    def submit_requisition(self, requisition_id: str) -> tuple[bool, str, dict]:
        return self._run("req_submit", actor_user_id=self._actor(),
                         requisition_id=requisition_id)

    def approve_requisition(self, requisition_id: str, *, approve=True,
                            reason="") -> tuple[bool, str, dict]:
        return self._run("req_approve", approver_user_id=self._actor(),
                         requisition_id=requisition_id, approve=approve, reason=reason)

    def create_rfq_from_requisition(self, requisition_id: str,
                                    supplier_ids: list[str]) -> tuple[bool, str, dict]:
        return self._run("rfq_create", actor_user_id=self._actor(),
                         requisition_id=requisition_id, supplier_ids=supplier_ids)

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

    def capture_invoice(self, **fields) -> tuple[bool, str, dict]:
        return self._run("inv_capture", actor_user_id=self._actor(), **fields)

    def match_invoice(self, invoice_id: str) -> tuple[bool, str, dict]:
        return self._run("inv_match", actor_user_id=self._actor(), invoice_id=invoice_id)

    def release_variance(self, invoice_id: str, *, captured_by_user_id,
                         reason) -> tuple[bool, str, dict]:
        return self._run("inv_release", releaser_user_id=self._actor(),
                         invoice_id=invoice_id, captured_by_user_id=captured_by_user_id,
                         reason=reason)

    def related_shipments(self) -> list[dict]:
        if self._logistics is None:
            return []
        return self._logistics.related_to_destination(
            branch_id=self.default_branch(), warehouse_id=self.default_warehouse())

    # ── compra en origen (Logistics workspace) ───────────────────────────────
    def _origin_run(self, fn, *args, **kwargs) -> tuple[bool, str, dict]:
        try:
            detail = fn(*args, **kwargs)
            return True, "Operación registrada", detail or {}
        except (ValueError, LookupError) as exc:
            return False, str(exc), {}
        except Exception:
            logger.exception("EnterprisePurchasingPresenter: error en compra en origen")
            return False, "Error inesperado; revise el log.", {}

    def origin_documents(self, search: str = "") -> list[dict]:
        if self._origin is None:
            raise PermissionError("Compra en origen no está configurada en este equipo")
        return self._origin.documents(branch_id=self.default_branch(),
                                      warehouse_id=self.default_warehouse(), search=search)

    def origin_workspace(self, shipment_id: str):
        if self._origin is None:
            raise PermissionError("Compra en origen no está configurada en este equipo")
        return self._origin.open(shipment_id)

    def origin_create_shipment(self, document: dict) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_run(self._origin.create_shipment, actor_user_id=self._actor(),
                                branch_id=self.default_branch(),
                                warehouse_id=self.default_warehouse(), document=document)

    def origin_mobile_handoff(self, shipment_id: str) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_run(self._origin.mobile_handoff, shipment_id)

    def origin_seal_root(self, shipment_id: str, node_id: str,
                         seal_code: str) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_run(self._origin.seal_root, actor_user_id=self._actor(),
                                shipment_id=shipment_id, node_id=node_id, seal_code=seal_code)

    def origin_dispatch(self, shipment_id: str) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_run(self._origin.dispatch, actor_user_id=self._actor(),
                                shipment_id=shipment_id)

    def origin_authorize_variance(self, shipment_id: str, source_line_id: str,
                                  reason: str) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_run(self._origin.authorize_variance, actor_user_id=self._actor(),
                                shipment_id=shipment_id, source_line_id=source_line_id,
                                reason=reason)

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
