"""SupplierEvaluationRepository — evaluations + their weighted dimension items."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.suppliers.entities import (
    SupplierEvaluation,
    SupplierEvaluationItem,
)
from backend.domain.suppliers.enums import EvaluationDimension
from backend.domain.suppliers.value_objects import SupplierRating
from backend.infrastructure.db.repositories.suppliers.base import SupplierRepositoryBase


class SupplierEvaluationRepository(SupplierRepositoryBase):
    def save(self, ev: SupplierEvaluation, *, operation_id: str | None = None) -> None:
        self._execute(
            "INSERT INTO supplier_evaluations (id, supplier_id, period, score, rating_grade,"
            " evaluated_by_user_id, comments, evidence_reference, operation_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ev.id, ev.supplier_id, ev.period, ev.score,
             ev.rating.grade.value if ev.rating else None, ev.evaluated_by_user_id,
             ev.comments, ev.evidence_reference, operation_id or ev.id, ev.created_at))
        for item in ev.items:
            self._execute(
                "INSERT INTO supplier_evaluation_items (id, evaluation_id, dimension, score,"
                " weight) VALUES (?,?,?,?,?)",
                (self._new_item_id(), ev.id, item.dimension.value, item.score,
                 str(item.weight) if item.weight is not None else "1"))

    def find_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one(
            "SELECT id, supplier_id, period, score, rating_grade FROM supplier_evaluations"
            " WHERE operation_id=?", (operation_id,))

    def latest_for_supplier(self, supplier_id: str) -> SupplierEvaluation | None:
        row = self._query_one(
            "SELECT id, supplier_id, period, score, rating_grade, evaluated_by_user_id,"
            " comments, evidence_reference, created_at FROM supplier_evaluations"
            " WHERE supplier_id=? ORDER BY period DESC LIMIT 1", (supplier_id,))
        if row is None:
            return None
        items = [
            SupplierEvaluationItem(EvaluationDimension(i["dimension"]), i["score"],
                                   Decimal(i["weight"]))
            for i in self._query(
                "SELECT dimension, score, weight FROM supplier_evaluation_items"
                " WHERE evaluation_id=?", (row["id"],))
        ]
        return SupplierEvaluation(
            id=row["id"], supplier_id=row["supplier_id"], period=row["period"], items=items,
            evaluated_by_user_id=row["evaluated_by_user_id"], comments=row["comments"],
            evidence_reference=row["evidence_reference"], score=row["score"],
            rating=SupplierRating.from_score(row["score"]) if row["rating_grade"] else None,
            created_at=row["created_at"])

    @staticmethod
    def _new_item_id() -> str:
        from backend.shared.ids import new_uuid
        return new_uuid()
