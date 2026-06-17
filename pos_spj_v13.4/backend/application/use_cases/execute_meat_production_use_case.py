"""ExecuteMeatProductionUseCase — orchestrates the full carnica batch lifecycle."""

from __future__ import annotations

import logging

from backend.application.commands.production_commands import ExecuteMeatProductionCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.use_cases.meat_production")


class ExecuteMeatProductionUseCase(BaseUseCase[ExecuteMeatProductionCommand]):
    """Orchestrate open-batch → add-outputs → close-batch via ProductionApplicationService.

    ProductionApplicationService (core/services/production_application_service.py)
    is injected — this use case never touches the DB directly.
    """

    name = "ExecuteMeatProductionUseCase"

    def __init__(self, production_service) -> None:
        self._svc = production_service

    def execute(self, command: ExecuteMeatProductionCommand) -> UseCaseResult:
        command.validate_context()

        if not command.product_id:
            return UseCaseResult(
                success=False,
                operation_id=command.operation_id,
                message="product_id is required",
            )
        if command.batch_weight_kg <= 0:
            return UseCaseResult(
                success=False,
                operation_id=command.operation_id,
                message="batch_weight_kg must be greater than zero",
            )

        branch_id = command.branch_id
        user = command.user_name or command.user_id or "sistema"

        try:
            opened = self._svc.abrir_lote(
                producto_origen_id=command.product_id,
                peso_kg=command.batch_weight_kg,
                sucursal_id=branch_id,
                usuario=user,
                receta_id=command.recipe_id or None,
            )
            if not getattr(opened, "ok", False):
                return UseCaseResult(
                    success=False,
                    operation_id=command.operation_id,
                    message=getattr(opened, "error", "No se pudo abrir lote"),
                )

            batch_id = opened.batch_id

            for output in command.outputs:
                pid = str(output["product_id"])
                kg = float(output["weight_kg"])
                self._svc.agregar_subproducto(
                    batch_id=batch_id,
                    producto_id=pid,
                    peso_kg=kg,
                    is_waste=False,
                )

            if command.waste_kg > 0:
                self._svc.agregar_subproducto(
                    batch_id=batch_id,
                    producto_id=command.product_id,
                    peso_kg=command.waste_kg,
                    is_waste=True,
                )

            result = self._svc.cerrar_lote(
                batch_id=batch_id,
                sucursal_id=branch_id,
                usuario=user,
            )
            if not getattr(result, "ok", False):
                return UseCaseResult(
                    success=False,
                    operation_id=command.operation_id,
                    message=getattr(result, "error", "No se pudo cerrar lote"),
                )

            folio = getattr(result, "folio", batch_id)
            rendimiento = getattr(result, "rendimiento_pct", 0.0)
            logger.info(
                "ExecuteMeatProductionUseCase operation_id=%s folio=%s rendimiento=%.2f%%",
                command.operation_id, folio, rendimiento,
            )
            return UseCaseResult(
                success=True,
                operation_id=command.operation_id,
                entity_id=str(batch_id),
                message=f"Lote {folio} cerrado — rendimiento {rendimiento:.2f}%",
                data={"batch_id": batch_id, "folio": folio, "rendimiento_pct": rendimiento},
            )

        except Exception as exc:
            logger.exception("ExecuteMeatProductionUseCase failed operation_id=%s", command.operation_id)
            return UseCaseResult(
                success=False,
                operation_id=command.operation_id,
                message=str(exc),
            )
