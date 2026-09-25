"""ProductionPlanRepository — el plan de producción de una sucursal por día (§11).

El plan y sus líneas se guardan juntos: guardar el plan reescribe sus líneas
(un plan es un agregado; sus líneas no existen fuera de él).
"""

from __future__ import annotations

import json

from backend.domain.meat_processing.entities.production_plan import ProductionPlan
from backend.domain.meat_processing.entities.production_plan_line import ProductionPlanLine
from backend.domain.meat_processing.enums import (
    PlanSourceType,
    ProcessType,
    ProductionPlanStatus,
)
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dec_str,
    dt_str,
    enum_value,
    now_iso,
    parse_dt,
    to_decimal,
)


def _line(row: dict) -> ProductionPlanLine:
    return ProductionPlanLine(
        id=row["id"], product_id=row["product_id"],
        source_type=PlanSourceType(row["source_type"]),
        planned_quantity=to_decimal(row["planned_quantity"]),
        planned_weight=to_decimal(row["planned_weight"]),
        source_reference_id=row["source_reference_id"],
        required_date=parse_dt(row["required_date"]), priority=int(row["priority"] or 0),
        converted_quantity=to_decimal(row["converted_quantity"]),
        converted_weight=to_decimal(row["converted_weight"]),
        converted_processing_order_ids=tuple(json.loads(row["converted_order_ids_json"] or "[]")),
        process_type=ProcessType(row["process_type"]) if row["process_type"] else None,
        target_product_id=row["target_product_id"])


class ProductionPlanRepository(MeatProcessingRepositoryBase):
    def save(self, plan: ProductionPlan) -> None:
        self._execute(
            "INSERT INTO production_plans (id, operation_id, branch_id, planning_period, status,"
            " created_by_user_id, approved_by_user_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " approved_by_user_id=excluded.approved_by_user_id, updated_at=excluded.updated_at",
            (plan.id, plan.operation_id, plan.branch_id, plan.planning_period,
             enum_value(plan.status), plan.created_by_user_id, plan.approved_by_user_id,
             dt_str(plan.created_at), now_iso()))
        self._execute("DELETE FROM production_plan_lines WHERE plan_id=?", (plan.id,))
        for orden, linea in enumerate(plan.lines):
            self._execute(
                "INSERT INTO production_plan_lines (id, plan_id, sequence, product_id,"
                " process_type, target_product_id, source_type, source_reference_id,"
                " planned_quantity, planned_weight, required_date, priority,"
                " converted_quantity, converted_weight, converted_order_ids_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (linea.id, plan.id, orden, linea.product_id, enum_value(linea.process_type),
                 linea.target_product_id, enum_value(linea.source_type),
                 linea.source_reference_id, dec_str(linea.planned_quantity),
                 dec_str(linea.planned_weight), dt_str(linea.required_date), linea.priority,
                 dec_str(linea.converted_quantity), dec_str(linea.converted_weight),
                 json.dumps(list(linea.converted_processing_order_ids))))

    def _hydrate(self, row: dict | None) -> ProductionPlan | None:
        if row is None:
            return None
        plan = ProductionPlan(
            id=row["id"], operation_id=row["operation_id"], branch_id=row["branch_id"],
            planning_period=row["planning_period"], created_by_user_id=row["created_by_user_id"],
            status=ProductionPlanStatus(row["status"]),
            approved_by_user_id=row["approved_by_user_id"],
            created_at=parse_dt(row["created_at"]))
        plan.lines = [_line(r) for r in self._query(
            "SELECT * FROM production_plan_lines WHERE plan_id=? ORDER BY sequence, id",
            (plan.id,))]
        return plan

    def get(self, plan_id: str) -> ProductionPlan | None:
        return self._hydrate(self._query_one("SELECT * FROM production_plans WHERE id=?",
                                             (plan_id,)))

    def get_for_day(self, branch_id: str, planning_period: str) -> ProductionPlan | None:
        return self._hydrate(self._query_one(
            "SELECT * FROM production_plans WHERE branch_id=? AND planning_period=?",
            (branch_id, planning_period)))

    def get_by_operation_id(self, operation_id: str) -> ProductionPlan | None:
        return self._hydrate(self._query_one(
            "SELECT * FROM production_plans WHERE operation_id=?", (operation_id,)))
