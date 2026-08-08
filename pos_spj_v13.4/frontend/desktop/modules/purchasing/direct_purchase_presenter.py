"""DirectPurchasePresenter — the only gateway between the direct-purchase UI and
the backend. Wires read services + use cases; never touches SQL/connections.

Totals shown in the cart are recomputed here from Decimal (never in the widget),
and every mutation is delegated to a use case (atomic, audited, event-emitting).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.shared.ids import new_uuid
from frontend.desktop.components.search_selector import SearchOption
from frontend.desktop.modules.purchasing.capability_resolver import (
    resolve_purchasing_capabilities,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import (
    CartLineVM,
    TableViewModel,
    money,
    payment_condition_es,
    status_es,
)
from frontend.desktop.modules.purchasing.enterprise_view_models import PurchasingCapabilities

logger = logging.getLogger("spj.purchasing.direct_presenter")

_PAGE_SIZE = 50


def _supplier_subtitle(row: dict) -> str:
    """Surface a financial block in the picker itself — never let the buyer
    choose a blocked supplier only to find out from a rejected submission."""
    if row.get("bloqueado_financiero"):
        return "Bloqueado financieramente"
    if not row.get("compras_habilitadas", True):
        return "Compras deshabilitadas"
    return row.get("code") or ""


class DirectPurchasePresenter:
    def __init__(self, *, connection_provider, read_service, supplier_picker,
                 use_cases: dict, session_context=None, templates=None, costs=None,
                 variance_policy=None, event_dispatcher=None, product_catalog=None) -> None:
        self._conn = connection_provider
        self._reads = read_service
        self._suppliers = supplier_picker
        self._use_cases = use_cases
        self._session = session_context
        self._templates = templates
        self._costs = costs
        self._variance = variance_policy
        self._dispatch = event_dispatcher
        self._product_catalog = product_catalog

    # session helpers ---------------------------------------------------------
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

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> PurchasingCapabilities:
        return resolve_purchasing_capabilities(self.can)

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
            logger.exception("DirectPurchasePresenter: error in %s", key)
            return False, "Error inesperado; revise el log.", {}

    # reads -------------------------------------------------------------------
    def supplier_options(self, query: str) -> list[SearchOption]:
        try:
            rows = self._suppliers.search(query)
        except Exception:
            logger.exception("supplier search failed")
            return []
        return [SearchOption(id=r["id"], label=r["name"], subtitle=_supplier_subtitle(r))
                for r in rows]

    def product_options(self, query: str) -> list[SearchOption]:
        if self._product_catalog is None:
            return []
        try:
            options = self._product_catalog.search(query, branch_id=self.default_branch())
        except Exception:
            logger.exception("product search failed")
            return []
        return [SearchOption(id=o.product_id, label=o.name, subtitle=o.code)
                for o in options]

    def purchases(self, *, status: str | None = None, search: str = "",
                  page: int = 0) -> TableViewModel:
        offset = max(0, page) * _PAGE_SIZE
        rows_data = self._reads.list(status=status, search=search, limit=_PAGE_SIZE,
                                     offset=offset)
        total = self._reads.count(status=status, search=search)
        rows, ids = [], []
        for r in rows_data:
            rows.append([r.document_number, r.supplier_name, status_es(r.status),
                         payment_condition_es(r.payment_condition), money(r.total),
                         (r.created_at or "")[:10]])
            ids.append(r.id)
        return TableViewModel(rows, ids, total=int(total))

    def detail(self, direct_purchase_id: str):
        return self._reads.get_detail(direct_purchase_id)

    def supplier_name(self, supplier_id: str) -> str:
        return self._reads.supplier_name(supplier_id)

    def session_destination(self) -> str:
        try:
            return f"{self.default_branch()} / {self.default_warehouse()}"
        except PermissionError:
            return "Selecciona sucursal y almacén"

    # cart totals (Decimal, in the presenter) ---------------------------------
    def totals(self, lines: list[CartLineVM]) -> dict:
        subtotal = sum((ln.line_subtotal() for ln in lines), Decimal("0"))
        tax = sum((ln.tax for ln in lines), Decimal("0"))
        discount = sum((ln.discount for ln in lines), Decimal("0"))
        total = sum((ln.line_total() for ln in lines), Decimal("0"))
        return {"subtotal": money(subtotal), "tax": money(tax), "discount": money(discount),
                "total": money(total)}

    # actions -----------------------------------------------------------------
    def create(self, *, supplier_id: str, lines: list[CartLineVM], mode: str,
               payment_condition: str, branch_id: str | None = None,
               warehouse_id: str | None = None,
               source_requisition_id: str | None = None) -> tuple[bool, str, dict]:
        try:
            actor_user_id = self._actor()
            resolved_branch_id = branch_id or self.default_branch()
            resolved_warehouse_id = warehouse_id or self.default_warehouse()
        except PermissionError as exc:
            return False, str(exc), {"error_code": "SESSION_CONTEXT_REQUIRED"}
        return self._run(
            "create", actor_user_id=actor_user_id, supplier_id=supplier_id,
            branch_id=resolved_branch_id, warehouse_id=resolved_warehouse_id,
            lines=[ln.as_payload() for ln in lines], mode=mode,
            payment_condition=payment_condition,
            source_requisition_id=source_requisition_id)

    def authorize(self, direct_purchase_id: str, reason: str) -> tuple[bool, str, dict]:
        return self._run("authorize", authorizer_user_id=self._actor(),
                         direct_purchase_id=direct_purchase_id, reason=reason)

    def confirm(self, direct_purchase_id: str,
                payment_source: str | None) -> tuple[bool, str, dict]:
        return self._run("confirm", actor_user_id=self._actor(),
                         direct_purchase_id=direct_purchase_id, payment_source=payment_source)

    def reverse(self, direct_purchase_id: str, reason: str) -> tuple[bool, str, dict]:
        return self._run("reverse", actor_user_id=self._actor(),
                         direct_purchase_id=direct_purchase_id, reason=reason)

    # templates (migrated from the legacy sidebar) ----------------------------
    def templates(self) -> list[dict]:
        if self._templates is None:
            return []
        try:
            return self._templates.list_templates()
        except Exception:
            logger.exception("templates list failed")
            return []

    def template_lines(self, template_id: str) -> list[CartLineVM]:
        if self._templates is None:
            return []
        from decimal import Decimal
        out: list[CartLineVM] = []
        for raw in self._templates.template_lines(template_id):
            out.append(CartLineVM(
                product_id=raw["product_id"], description=raw["product_id"],
                quantity=Decimal(str(raw["quantity"])),
                unit_cost=Decimal(str(raw["unit_cost"]))))
        return out

    # cost-variance alert (migrated from the legacy monolith) -----------------
    def historical_cost(self, product_id: str):
        if self._costs is None:
            return "0"
        try:
            return self._costs.historical_cost(product_id, branch_id=self.default_branch())
        except Exception:
            logger.exception("historical cost lookup failed")
            return "0"

    def price_variance(self, product_id: str, captured_cost) -> dict:
        """Display-ready live variance for the add-line dialog (▲ SUBIÓ 25.0%)."""
        if self._variance is None:
            return {"label": "—", "is_significant": False, "percent": "0"}
        result = self._variance.evaluate(self.historical_cost(product_id), captured_cost)
        return {"label": result.label(), "is_significant": result.is_significant,
                "percent": str(result.percent)}

    def record_price_variances(self, *, document_id, lines: list[CartLineVM]
                               ) -> list[dict]:
        """After a save, record significant variances canonically (audit + event)."""
        if "record_variance" not in self._use_cases:
            return []
        payload = [{"product_id": ln.product_id, "captured_cost": str(ln.unit_cost)}
                   for ln in lines]
        ok, _msg, data = self._run("record_variance", actor_user_id=self._actor(),
                                   document_id=document_id, lines=payload,
                                   branch_id=self.default_branch())
        return data.get("detected", []) if ok else []
