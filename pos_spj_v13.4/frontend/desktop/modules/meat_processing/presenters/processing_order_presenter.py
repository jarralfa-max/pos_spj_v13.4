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

#: Estados de la orden en español. Público: el Resumen lee ESTA tabla en vez
#: de repetirla, para que las dos pantallas llamen igual al mismo estado.
ORDER_STATUS_LABELS = {
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
                 event_dispatcher=None, warehouse_provider=None, plan_query=None,
                 execute_uc=None, credentials_verifier=None, tolerances_query=None,
                 tolerances_uc=None) -> None:
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
        #: Fase 10: almacén de producción de la sucursal, ejecución de la orden,
        #: verificación del autorizador y tolerancias de rendimiento.
        self._warehouse_provider = warehouse_provider
        self._plan_query = plan_query
        self._execute_uc = execute_uc
        self._credentials = credentials_verifier
        self._tolerances_query = tolerances_query
        self._tolerances_uc = tolerances_uc

    def _actor(self) -> str:
        return str(getattr(self._session, "user_id", None) or "")

    def _context(self):
        return self._context_provider() if self._context_provider is not None else None

    def default_branch(self) -> str:
        session = self._session
        return str(getattr(session, "active_branch_id", None)
                   or getattr(session, "branch_id", None) or "")

    def default_warehouse(self) -> str:
        return self.warehouse_and_problem()[0] or ""

    def warehouse_and_problem(self) -> tuple[str | None, str | None]:
        """(almacén de producción, motivo si no hay). La sesión no trae almacén:
        se resuelve el ACTIVO de la sucursal marcado «Producción» (Fase 10)."""
        session = self._session
        de_sesion = str(getattr(session, "active_warehouse_id", None)
                        or getattr(session, "warehouse_id", None) or "")
        if de_sesion:
            return de_sesion, None
        if self._warehouse_provider is None:
            return None, "La sesión no tiene almacén activo."
        return self._warehouse_provider()

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
                ORDER_STATUS_LABELS.get(order.status.value, order.status.value),
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
        # Una orden de despiece se planea por PESO; el campo de cantidad queda
        # vacío y `DecimalInput` devuelve None, que el caso de uso rechazaba
        # ("planned_quantity no es decimal válido").
        from decimal import Decimal as _D
        planned_quantity = planned_quantity if planned_quantity is not None else _D("0")
        planned_weight = planned_weight if planned_weight is not None else _D("0")
        branch = self.default_branch()
        warehouse, problema = self.warehouse_and_problem()
        if not branch:
            return False, "La sesión no tiene sucursal activa.", {}
        if not warehouse:
            return False, problema or "La sucursal no tiene almacén de producción.", {}
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

    # ── ejecución (Fase 10) ────────────────────────────────────────────────
    def execution_plan(self, order_id: str) -> dict | None:
        """Entrada y salidas ESPERADAS del despiece capturado al liberar."""
        if self._plan_query is None:
            return None
        try:
            return self._plan_query().plan(order_id)
        except Exception:
            logger.exception("plan de ejecución no disponible")
            return None

    def execute_order(self, *, order_id: str, input_weight, outputs: list[dict],
                      stock_authorizer_user_id=None, stock_reason=None,
                      variance_authorizer_user_id=None,
                      variance_reason=None) -> tuple[bool, str, dict]:
        if self._execute_uc is None:
            return False, "Ejecución de órdenes no disponible.", {}
        try:
            result = self._execute_uc.execute(
                self._conn(), order_id=order_id, input_weight=input_weight, outputs=outputs,
                actor_user_id=self._actor(), operation_id=new_uuid(),
                stock_authorizer_user_id=stock_authorizer_user_id, stock_reason=stock_reason,
                variance_authorizer_user_id=variance_authorizer_user_id,
                variance_reason=variance_reason, context=self._context())
        except Exception:
            logger.exception("ProcessingOrderPresenter.execute_order failed")
            return False, "Error inesperado; revise el log.", {}
        if result.success and self._dispatch is not None:
            try:
                self._dispatch()
            except Exception:
                logger.exception("post-commit dispatch failed")
        datos = dict(result.data)
        if result.error_code:
            datos["error_code"] = result.error_code
        return bool(result.success), result.message, datos

    def verify_authorizer(self, usuario: str, clave: str) -> tuple[str | None, str]:
        """(user_id, "") si usuario y clave son de un usuario activo; el permiso
        lo revalida el caso de uso."""
        if self._credentials is None:
            return None, "La verificación del autorizador no está disponible."
        from backend.security.authentication.errors import AuthenticationFailedError
        from backend.security.sessions.errors import AccountLockedError
        try:
            return self._credentials(username=usuario, password=clave), ""
        except (AuthenticationFailedError, AccountLockedError) as exc:
            return None, str(exc)

    # ── tolerancias de rendimiento (Fase 10) ───────────────────────────────
    def yield_tolerances(self) -> dict:
        if self._tolerances_query is None:
            return {}
        try:
            t = self._tolerances_query().get()
        except Exception:
            logger.exception("tolerancias no disponibles")
            return {}
        return {"warning_pct": t.warning_pct, "tolerance_pct": t.tolerance_pct,
                "critical_pct": t.critical_pct}

    def save_yield_tolerances(self, *, warning_pct, tolerance_pct,
                              critical_pct) -> tuple[bool, str]:
        if self._tolerances_uc is None:
            return False, "Configuración no disponible."
        try:
            return self._tolerances_uc.execute(
                self._conn(), actor_user_id=self._actor(), warning_pct=warning_pct,
                tolerance_pct=tolerance_pct, critical_pct=critical_pct)
        except Exception:
            logger.exception("guardar tolerancias falló")
            return False, "Error inesperado; revise el log."

    def close_order(self, *, order_id: str) -> tuple[bool, str, dict]:
        return self._transition(
            self._close_uc, order_id,
            unavailable_message="Cierre de órdenes no disponible.")
