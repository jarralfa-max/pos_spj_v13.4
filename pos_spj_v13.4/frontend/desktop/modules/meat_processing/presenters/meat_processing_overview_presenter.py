"""MeatProcessingOverviewPresenter (Resumen) — formato de los indicadores.

No cuenta nada: los números salen de `MeatProcessingOverviewQueryService`, que a
su vez reusa los contadores del sidebar. Aquí sólo se decide cómo se llaman en
español, en qué orden se enseñan y cuándo un número pinta en rojo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.application.meat_processing.queries.meat_processing_overview_query_service import (
    MeatProcessingOverviewQueryService,
)
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.modules.meat_processing.presenters.processing_order_presenter import (
    ORDER_STATUS_LABELS,
)

#: Contador del Resumen → (título, icono, si el número distinto de cero alarma).
ATTENTION_KPIS: tuple[tuple[str, str, str, bool], ...] = (
    ("orders_needing_attention", "Órdenes por atender", "orders", True),
    ("active_orders", "En proceso", "activity", False),
    ("yield_out_of_tolerance", "Rendimiento fuera de tolerancia", "yield", True),
    ("pending_quality", "Calidad pendiente", "quality", True),
    ("open_incidents", "Incidencias abiertas", "incident", True),
)

OUTPUT_TYPE_LABELS: dict[str, str] = {
    "MAIN_PRODUCT": "Producto principal", "CO_PRODUCT": "Coproducto",
    "BY_PRODUCT": "Subproducto", "SEMI_FINISHED": "Semielaborado",
    "WORK_IN_PROGRESS": "En proceso", "REWORKABLE": "Reprocesable",
    "WASTE": "Desperdicio", "LOSS": "Merma",
}


@dataclass(slots=True)
class OverviewTableModel:
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OverviewViewModel:
    kpis: list[KPIDTO] = field(default_factory=list)
    by_status: OverviewTableModel = field(default_factory=OverviewTableModel)
    production: OverviewTableModel = field(default_factory=OverviewTableModel)
    period: str = ""


def _peso(valor) -> str:
    try:
        numero = Decimal(str(valor or "0"))
    except InvalidOperation:
        return str(valor)
    return f"{numero.normalize():f} kg" if numero else "—"


def _cantidad(valor) -> str:
    try:
        numero = Decimal(str(valor or "0"))
    except InvalidOperation:
        return str(valor)
    return f"{numero.normalize():f}" if numero else "—"


class MeatProcessingOverviewPresenter:
    def __init__(self, connection, *, branch_id: str,
                 service_factory=MeatProcessingOverviewQueryService) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._service_factory = service_factory

    def overview(self, *, days: int = 7) -> OverviewViewModel:
        resumen = self._service_factory(self._conn).overview(self._branch_id, days=days)
        total_ordenes = sum(fila.count for fila in resumen.by_status)
        return OverviewViewModel(
            kpis=[
                KPIDTO(key=clave, title=titulo, value=str(resumen.attention.get(clave, 0)),
                       icon=icono,
                       variant=("danger" if alarma and resumen.attention.get(clave, 0)
                                else "primary"))
                for clave, titulo, icono, alarma in ATTENTION_KPIS
            ],
            by_status=OverviewTableModel(
                rows=[[ORDER_STATUS_LABELS.get(fila.status, fila.status), str(fila.count),
                       _porcentaje(fila.count, total_ordenes)]
                      for fila in resumen.by_status],
                row_ids=[fila.status for fila in resumen.by_status]),
            production=OverviewTableModel(
                rows=[[OUTPUT_TYPE_LABELS.get(fila.output_type, fila.output_type),
                       str(fila.outputs), _cantidad(fila.quantity), _peso(fila.weight)]
                      for fila in resumen.production],
                row_ids=[fila.output_type for fila in resumen.production]),
            period=f"Salidas de los últimos {resumen.days} día(s).")


def _porcentaje(parte: int, total: int) -> str:
    return f"{parte * 100 // total}%" if total else "—"
