"""El plan de producción de una sucursal para un día, listo para mostrarse:
productos por su nombre, lo planeado y lo ya convertido en órdenes (con folio)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)


@dataclass(frozen=True)
class PlanLineView:
    line_id: str
    product_name: str
    process_type: str | None
    target_name: str
    planned_weight: Decimal
    planned_quantity: Decimal
    converted_weight: Decimal
    converted_quantity: Decimal
    source_type: str
    priority: int
    required_date: str
    order_folios: tuple[str, ...]
    convertible: bool

    @property
    def remaining_weight(self) -> Decimal:
        return self.planned_weight - self.converted_weight


@dataclass(frozen=True)
class PlanView:
    plan_id: str
    planning_period: str
    status: str
    created_by_user_id: str
    approved_by_user_id: str | None
    lines: tuple[PlanLineView, ...] = field(default_factory=tuple)


class ProductionPlanQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _names(self, ids) -> dict[str, str]:
        nombres = {}
        for pid in {i for i in ids if i}:
            fila = self._conn.execute("SELECT name FROM products WHERE id=?", (pid,)).fetchone()
            nombres[pid] = str(fila[0]) if fila and fila[0] else "Producto no registrado"
        return nombres

    def _folios(self, order_ids) -> dict[str, str]:
        folios = {}
        for oid in order_ids:
            fila = self._conn.execute("SELECT folio FROM processing_orders WHERE id=?",
                                      (oid,)).fetchone()
            folios[oid] = str(fila[0]) if fila and fila[0] else "Orden sin folio"
        return folios

    def for_day(self, branch_id: str, planning_period: str) -> PlanView | None:
        plan = MeatProcessingUnitOfWork(self._conn).production_plans.get_for_day(
            branch_id, planning_period)
        if plan is None:
            return None
        nombres = self._names([l.product_id for l in plan.lines]
                              + [l.target_product_id for l in plan.lines])
        folios = self._folios([o for l in plan.lines for o in l.converted_processing_order_ids])
        return PlanView(
            plan_id=plan.id, planning_period=plan.planning_period, status=plan.status.value,
            created_by_user_id=plan.created_by_user_id,
            approved_by_user_id=plan.approved_by_user_id,
            lines=tuple(PlanLineView(
                line_id=l.id, product_name=nombres[l.product_id],
                process_type=l.process_type.value if l.process_type else None,
                target_name=nombres.get(l.target_product_id, "—"),
                planned_weight=l.planned_weight, planned_quantity=l.planned_quantity,
                converted_weight=l.converted_weight, converted_quantity=l.converted_quantity,
                source_type=l.source_type.value, priority=l.priority,
                required_date=l.required_date.date().isoformat() if l.required_date else "",
                order_folios=tuple(folios[o] for o in l.converted_processing_order_ids),
                convertible=l.is_convertible) for l in plan.lines))
