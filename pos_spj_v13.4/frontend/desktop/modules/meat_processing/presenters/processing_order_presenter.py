"""Presentation orchestration for the Procesamiento Cárnico Órdenes page
(PROC-23, first functional page — the rest of MEAT_PROCESSING_NAV stays on
the PROC-4 placeholder until built incrementally). Mirrors
frontend/desktop/modules/inventory/presenter.py's shape: queries return
TableViewModel, commands return (ok, message, data); every command
re-validates its own permission on the backend (hiding a button is not
security) — this presenter only shapes what the page shows/enables.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid
from frontend.desktop.modules.meat_processing.view_models import TableViewModel

logger = logging.getLogger("spj.ui.meat_processing")

_STATUS_ES = {
    "DRAFT": "Borrador", "PENDING_APPROVAL": "Por aprobar", "APPROVED": "Aprobada",
    "MATERIALS_PENDING": "Esperando materiales", "READY": "Lista",
    "RELEASED": "Liberada", "IN_PROGRESS": "En proceso", "PAUSED": "Pausada",
    "PARTIALLY_COMPLETED": "Parcialmente completada",
    "PENDING_QUALITY": "Esperando calidad",
    "PENDING_RECONCILIATION": "Esperando conciliación", "COMPLETED": "Completada",
    "CLOSED": "Cerrada", "CANCELLED": "Cancelada", "REVERSED": "Reversada",
}

_PROCESS_TYPE_ES = {
    "CUTTING": "Corte", "DISASSEMBLY": "Despiece", "DEBONING": "Deshuesado",
    "TRIMMING": "Recorte", "PORTIONING": "Porcionado", "GRINDING": "Molido",
    "MIXING": "Mezclado", "MARINATION": "Marinado", "FORMULATION": "Formulación",
    "PACKAGING": "Empaque", "REPACKAGING": "Reempaque", "LABELING": "Etiquetado",
    "FREEZING": "Congelado", "THAWING": "Descongelado", "CHILLING": "Enfriado",
}


class ProcessingOrderPresenter:
    def __init__(self, *, connection_provider, query_factory, product_query_factory=None,
                 create_uc=None, approve_uc=None, release_uc=None, close_uc=None,
                 session_context=None, context_provider=None,
                 event_dispatcher=None) -> None:
        self._conn = connection_provider
        self._query_factory = query_factory
        self._product_factory = product_query_factory
        self._create_uc = create_uc
        self._approve_uc = approve_uc
        self._release_uc = release_uc
        self._close_uc = close_uc
        self._session = session_context
        self._context_provider = context_provider
        self._dispatch = event_dispatcher

    def _actor(self) -> str:
        return str(getattr(self._session, "user_id", None) or "")

    def _context(self):
        return self._context_provider() if self._context_provider is not None else None

    def default_branch(self) -> str:
        session = self._session
        return str(getattr(session, "active_branch_id", None)
                   or getattr(session, "branch_id", None) or "")

    def default_warehouse(self) -> str:
        session = self._session
        return str(getattr(session, "active_warehouse_id", None)
                   or getattr(session, "warehouse_id", None) or "")

    def process_types(self) -> list[tuple[str, str]]:
        return sorted(_PROCESS_TYPE_ES.items(), key=lambda item: item[1])

    def product_options(self, query: str):
        from frontend.desktop.components.search_selector import SearchOption
        if self._product_factory is None:
            return []
        try:
            results = self._product_factory(self._conn()).search_products(query)
        except Exception:
            logger.exception("ProcessingOrderPresenter.product_options failed")
            return []
        return [SearchOption(id=r.id, label=r.label, subtitle=r.subtitle) for r in results]

    def orders(self, *, branch_id: str | None = None) -> TableViewModel:
        branch = branch_id or self.default_branch()
        if not branch:
            return TableViewModel()
        try:
            rows = self._query_factory(self._conn()).list_by_branch(branch)
        except Exception:
            logger.exception("ProcessingOrderPresenter.orders failed")
            return TableViewModel()
        out, ids = [], []
        for order in rows:
            ids.append(order.id)
            out.append([
                _PROCESS_TYPE_ES.get(order.process_type.value, order.process_type.value),
                _STATUS_ES.get(order.status.value, order.status.value),
                str(order.planned_quantity), str(order.planned_weight),
                order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else "",
            ])
        return TableViewModel(rows=out, row_ids=ids, total=len(out))

    @staticmethod
    def _result_data(result) -> dict:
        data = dict(result.data)
        if result.entity_id is not None:
            data.setdefault("entity_id", result.entity_id)
        return data

    def create_order(self, *, process_type: str, target_product_id: str,
                      planned_quantity, planned_weight) -> tuple[bool, str, dict]:
        if self._create_uc is None:
            return False, "Creación de órdenes no disponible.", {}
        product = str(target_product_id or "").strip()
        if not product:
            return False, "Selecciona un producto.", {}
        try:
            from backend.domain.meat_processing.enums import ProcessType
            process_enum = ProcessType(str(process_type))
        except ValueError:
            return False, "Tipo de proceso inválido.", {}
        if not planned_quantity and not planned_weight:
            return False, "Captura cantidad o peso planeado.", {}
        branch = self.default_branch()
        warehouse = self.default_warehouse()
        if not branch or not warehouse:
            return False, "Sesión sin sucursal/almacén activo.", {}
        try:
            result = self._create_uc.execute(
                self._conn(), operation_id=new_uuid(), branch_id=branch,
                warehouse_id=warehouse, process_type=process_enum,
                target_product_id=product, planned_quantity=planned_quantity,
                planned_weight=planned_weight, actor_user_id=self._actor(),
                context=self._context())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("ProcessingOrderPresenter.create_order failed")
            return False, "Error inesperado; revise el log.", {}

    def _transition(self, use_case, order_id: str, *,
                     unavailable_message: str) -> tuple[bool, str, dict]:
        if use_case is None:
            return False, unavailable_message, {}
        oid = str(order_id or "").strip()
        if not oid:
            return False, "Selecciona una orden.", {}
        try:
            result = use_case.execute(
                self._conn(), order_id=oid, operation_id=new_uuid(),
                actor_user_id=self._actor(), context=self._context())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("ProcessingOrderPresenter transition failed")
            return False, "Error inesperado; revise el log.", {}

    def approve_order(self, *, order_id: str) -> tuple[bool, str, dict]:
        return self._transition(
            self._approve_uc, order_id,
            unavailable_message="Aprobación de órdenes no disponible.")

    def release_order(self, *, order_id: str) -> tuple[bool, str, dict]:
        return self._transition(
            self._release_uc, order_id,
            unavailable_message="Liberación de órdenes no disponible.")

    def close_order(self, *, order_id: str) -> tuple[bool, str, dict]:
        return self._transition(
            self._close_uc, order_id,
            unavailable_message="Cierre de órdenes no disponible.")
