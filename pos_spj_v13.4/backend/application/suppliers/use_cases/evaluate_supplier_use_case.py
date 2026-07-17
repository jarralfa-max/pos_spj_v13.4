"""EvaluateSupplier — scorecard evaluation. The score is computed in the domain
(never in the widget); the master's rating projection is updated for filtering.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.suppliers.authorization import SupplierAuthorizationPolicy
from backend.application.suppliers.permissions import SupplierPermissions
from backend.application.suppliers.result import SupplierResult
from backend.application.suppliers.use_cases.lifecycle_use_cases import _BaseUseCase
from backend.domain.suppliers.entities import (
    SupplierEvaluation,
    SupplierEvaluationItem,
)
from backend.domain.suppliers.enums import EvaluationDimension
from backend.domain.suppliers.events import SupplierEvents
from backend.domain.suppliers.exceptions import PermissionDeniedError, SupplierDomainError
from backend.domain.suppliers.value_objects import RatingBands
from backend.infrastructure.db.repositories.suppliers.unit_of_work import SupplierUnitOfWork


class EvaluateSupplierUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, supplier_id: str, period: str,
                items: list[dict], operation_id: str, comments: str = "",
                evidence_reference: str | None = None,
                bands: dict | None = None) -> SupplierResult:
        """``items``: [{"dimension": "QUALITY", "score": 90, "weight": "2"}, ...]."""
        try:
            self._auth.require(actor_user_id, SupplierPermissions.EVALUATE)
        except PermissionDeniedError as exc:
            return SupplierResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with SupplierUnitOfWork(connection) as uow:
            if uow.suppliers.get(supplier_id) is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            if uow.evaluations.find_by_operation_id(operation_id) is not None:
                return SupplierResult.ok("Evaluación ya registrada", operation_id=operation_id)
            try:
                domain_items = [
                    SupplierEvaluationItem(
                        EvaluationDimension(i["dimension"]), int(i["score"]),
                        Decimal(str(i.get("weight", "1"))))
                    for i in items
                ]
                rating_bands = RatingBands(**bands) if bands else None
                evaluation = SupplierEvaluation.create(
                    supplier_id, period, domain_items, actor_user_id,
                    bands=rating_bands, comments=comments, evidence_reference=evidence_reference)
            except (SupplierDomainError, ValueError, KeyError) as exc:
                return SupplierResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.evaluations.save(evaluation, operation_id=operation_id)
            # denormalized rating projection on the master (for filtering/sorting)
            if evaluation.rating is not None:
                uow.suppliers.update_rating(supplier_id, evaluation.rating.grade.value,
                                            evaluation.score)
            uow.audit.record(action=SupplierEvents.EVALUATED, actor_user_id=actor_user_id,
                             supplier_id=supplier_id, reason=period, operation_id=operation_id)
            self._emit(uow, SupplierEvents.EVALUATED, supplier_id, operation_id, actor_user_id,
                       period=period, score=evaluation.score,
                       rating=evaluation.rating.grade.value if evaluation.rating else None)
        return SupplierResult.ok("Evaluación registrada", entity_id=evaluation.id,
                                 operation_id=operation_id, score=evaluation.score,
                                 rating=evaluation.rating.grade.value if evaluation.rating else None)
