"""Plan de producción: lo que la pantalla muestra y pide. No calcula ni decide;
los casos de uso validan y los permisos se revalidan en ellos."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from backend.shared.ids import new_uuid
from frontend.desktop.modules.meat_processing.presenters.meat_processing_record_presenter import (  # noqa: E501
    PROCESS_TYPE_LABELS,
)

logger = logging.getLogger("spj.ui.meat_processing.plan")

PLAN_STATUS_LABELS = {
    "DRAFT": "Borrador", "GENERATED": "Generado", "UNDER_REVIEW": "En revisión",
    "APPROVED": "Aprobado", "PARTIALLY_CONVERTED": "Convertido en parte",
    "CONVERTED": "Convertido", "CANCELLED": "Cancelado",
}
SOURCE_LABELS = {
    "MANUAL": "Manual", "REPLENISHMENT": "Reposición", "FORECAST": "Pronóstico",
    "CUSTOMER_ORDER": "Pedido", "MINIMUM_STOCK": "Mínimo", "SALES_PLAN": "Plan de ventas",
    "REWORK": "Reproceso", "INTERNAL_REQUIREMENT": "Requerimiento interno",
}
#: Qué acciones tienen sentido en cada estado (la regla la aplica el dominio;
#: esto sólo habilita botones).
ACTIONS_BY_STATUS = {
    "DRAFT": {"add", "remove", "generate", "cancel"},
    "GENERATED": {"add", "remove", "submit", "cancel"},
    "UNDER_REVIEW": {"approve", "cancel"},
    "APPROVED": {"convert", "cancel"},
    "PARTIALLY_CONVERTED": {"convert", "cancel"},
    "CONVERTED": set(), "CANCELLED": set(),
}


def _kg(valor: Decimal) -> str:
    return f"{Decimal(valor).normalize():f} kg" if valor else "—"


@dataclass
class PlanViewModel:
    plan_id: str | None = None
    summary: str = ""
    status: str | None = None
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)
    actions: set[str] = field(default_factory=set)


class ProductionPlanPresenter:
    def __init__(self, *, connection_provider, session_context, query_factory, use_cases: dict,
                 suggestion_sources: dict | None = None, warehouse_provider=None,
                 context_provider=None) -> None:
        self._conn = connection_provider
        self._session = session_context
        self._query = query_factory
        self._uc = use_cases
        self._sources = suggestion_sources or {}
        self._warehouse = warehouse_provider
        self._context_provider = context_provider

    def _actor(self) -> str:
        return str(getattr(self._session, "user_id", "") or "")

    def branch(self) -> str:
        return str(getattr(self._session, "active_branch_id", "") or "")

    def _context(self):
        return self._context_provider() if self._context_provider else None

    # ── lectura ──────────────────────────────────────────────────────────
    def plan(self, day: date) -> PlanViewModel:
        vista = self._query(self._conn()).for_day(self.branch(), day.isoformat())
        if vista is None:
            return PlanViewModel(summary=f"No hay plan para el {day.isoformat()}.",
                                 actions={"create"})
        filas = []
        for l in vista.lines:
            convertido = (", ".join(l.order_folios) if l.order_folios else "—")
            filas.append([
                l.product_name,
                PROCESS_TYPE_LABELS.get(l.process_type, l.process_type or "Sin proceso"),
                l.target_name, _kg(l.planned_weight), _kg(l.converted_weight), convertido,
                SOURCE_LABELS.get(l.source_type, l.source_type), str(l.priority)])
        estado = PLAN_STATUS_LABELS.get(vista.status, vista.status)
        return PlanViewModel(
            plan_id=vista.plan_id, status=vista.status,
            summary=f"Plan del {vista.planning_period} · {estado} · {len(filas)} línea(s)",
            rows=filas, row_ids=[l.line_id for l in vista.lines],
            actions=set(ACTIONS_BY_STATUS.get(vista.status, set())))

    def process_types(self) -> list[tuple[str, str]]:
        from backend.domain.meat_processing.entities.processing_recipe_snapshot import (
            PROCESS_FAMILIES,
        )
        return sorted(((p.value, PROCESS_TYPE_LABELS.get(p.value, p.value))
                       for p in PROCESS_FAMILIES), key=lambda x: x[1])

    @staticmethod
    def needs_input_product(process_type: str) -> bool:
        """En despiece la orden transforma OTRO producto (la entrada); en los
        demás procesos, el objetivo es el mismo producto demandado."""
        from backend.domain.meat_processing.entities.processing_recipe_snapshot import (
            ProcessFamily,
            process_family,
        )
        from backend.domain.meat_processing.enums import ProcessType
        try:
            return process_family(ProcessType(process_type)) is ProcessFamily.DISASSEMBLY
        except ValueError:
            return False

    # ── búsqueda estándar de productos ───────────────────────────────────
    def _search(self, query: str, *, producible: bool):
        from backend.application.products.queries.product_selection_query_service import (
            ProductCatalogSearchQueryService,
            ProductSearchQuery,
            SearchProductionInputsQueryService,
        )
        criterio = ProductSearchQuery(text=(query or "").strip() or None,
                                      branch_id=self.branch() or None, page_size=50)
        if producible:
            return ProductCatalogSearchQueryService(self._conn()), criterio.restrict(
                producible_only=True)
        return SearchProductionInputsQueryService(self._conn()), criterio

    def product_options(self, query: str):
        """Producto DEMANDADO: lo que se necesita producir (producible)."""
        from frontend.desktop.components.search_selector import SearchOption
        servicio, criterio = self._search(query, producible=True)
        return [SearchOption(d.product_id, d.name, d.code or "") for d in servicio.search(criterio)]

    def input_options(self, query: str):
        """Entrada del despiece (insumo de producción)."""
        from frontend.desktop.components.search_selector import SearchOption
        servicio, criterio = self._search(query, producible=False)
        return [SearchOption(d.product_id, d.name, d.code or "") for d in servicio.search(criterio)]

    def product_search_reason(self, query: str, *, producible: bool = True):
        try:
            servicio, criterio = self._search(query, producible=producible)
            razon = servicio.explain_empty(criterio)
        except Exception:
            return None
        return razon.message if razon is not None else None

    # ── acciones ─────────────────────────────────────────────────────────
    def _run(self, nombre: str, **kwargs) -> tuple[bool, str, dict]:
        caso = self._uc.get(nombre)
        if caso is None:
            return False, "Acción no disponible.", {}
        try:
            r = caso.execute(self._conn(), operation_id=new_uuid(),
                             actor_user_id=self._actor(), context=self._context(), **kwargs)
        except Exception:
            logger.exception("plan: %s falló", nombre)
            return False, "Error inesperado; revise el log.", {}
        return r.success, r.message, dict(r.data)

    def create_plan(self, day: date):
        return self._run("create", branch_id=self.branch(), planning_date=day)

    def add_line(self, plan_id: str, **datos):
        return self._run("add_line", plan_id=plan_id, **datos)

    def remove_line(self, plan_id: str, line_id: str):
        return self._run("remove_line", plan_id=plan_id, line_id=line_id)

    def transition(self, accion: str, plan_id: str):
        return self._run(accion, plan_id=plan_id)

    def convert_line(self, plan_id: str, line_id: str, planned_weight=None):
        almacen, problema = (self._warehouse() if self._warehouse else (None, None))
        if not almacen:
            return False, problema or "La sucursal no tiene almacén de producción.", {}
        return self._run("convert", plan_id=plan_id, line_id=line_id, warehouse_id=almacen,
                         planned_weight=planned_weight)

    # ── sugerencias ──────────────────────────────────────────────────────
    def suggestion_sources(self) -> list[tuple[str, str]]:
        return [(clave, fabrica.label) for clave, fabrica in self._sources.items()]

    def suggestions(self, source_key: str):
        """(sugerencias, nota): la nota explica por qué no hay."""
        fabrica = self._sources.get(source_key)
        if fabrica is None:
            return [], "Fuente de sugerencias no disponible."
        fuente = fabrica(self._conn())
        try:
            lista = fuente.suggestions(self.branch())
        except Exception as exc:  # noqa: BLE001 — la pantalla lo dice, no revienta
            logger.exception("sugerencias de %s fallaron", source_key)
            return [], f"No se pudieron obtener sugerencias: {exc}"
        return lista, getattr(fuente, "note", None)
