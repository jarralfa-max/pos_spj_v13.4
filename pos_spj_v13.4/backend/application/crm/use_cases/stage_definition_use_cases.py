"""Configuración del pipeline (§20, CRM-43): alta, edición, orden y retiro de
etapas de ``crm_stage_definitions``.

El pipeline ya era DATO (la migración 183 siembra 6 etapas) pero no había
forma de cambiarlo sin tocar la base: la propia entidad lo dejaba «para la
fase que construya la pantalla». Permiso: ``CRM.pipeline.configurar``.

Reglas que se cuidan aquí (no en la pantalla):
* siempre queda al menos una etapa abierta, una ganada y una perdida activas
  (Ganar/Perder una oportunidad aterriza en esas etapas);
* no se retira una etapa con oportunidades abiertas;
* el código es único y no cambia (lo referencian reglas e historial).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.stage_definition import CRMStageDefinition
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork

STAGE_CONFIGURED = "CRM_PIPELINE_STAGE_CONFIGURED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_bounds(probability: int, min_activities: int) -> str | None:
    if not 0 <= int(probability) <= 100:
        return "La probabilidad debe estar entre 0 y 100."
    if int(min_activities) < 0:
        return "Las actividades mínimas no pueden ser negativas."
    return None


def _terminal_guard(stages: list[CRMStageDefinition]) -> str | None:
    active = [s for s in stages if s.active]
    if not any(s.is_won_stage for s in active):
        return "Debe quedar una etapa activa marcada como ganada."
    if not any(s.is_lost_stage for s in active):
        return "Debe quedar una etapa activa marcada como perdida."
    if not any(not s.is_terminal() for s in active):
        return "Debe quedar al menos una etapa abierta."
    return None


class _Base:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def _deny(self, actor_user_id: str, operation_id: str) -> CRMResult | None:
        try:
            self._auth.require(actor_user_id, CRMPermissions.PIPELINE_CONFIGURE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        return None

    @staticmethod
    def _audit(uow, actor_user_id: str, stage: CRMStageDefinition, reason: str,
               operation_id: str) -> None:
        uow.audit.record(action=STAGE_CONFIGURED, actor_user_id=actor_user_id,
                         after_json=json.dumps({
                             "stage_id": stage.id, "code": stage.code, "name": stage.name,
                             "order": stage.sequence_order,
                             "probability": stage.probability_default,
                             "min_activities": stage.min_activities,
                             "active": stage.active}),
                         reason=reason, operation_id=operation_id)


class CreateStageDefinitionUseCase(_Base):
    def execute(self, connection, *, actor_user_id: str, code: str, name: str,
                operation_id: str, probability_default: int = 0, is_won_stage: bool = False,
                is_lost_stage: bool = False, min_activities: int = 0,
                required_fields: tuple[str, ...] = ()) -> CRMResult:
        denied = self._deny(actor_user_id, operation_id)
        if denied:
            return denied
        problem = _check_bounds(probability_default, min_activities)
        if problem:
            return CRMResult.fail(problem, "VALIDATION", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            if code and uow.stage_definitions.get_by_code(code) is not None:
                return CRMResult.fail(f"Ya existe una etapa con el código {code.upper()}.",
                                      "DUPLICATE", operation_id=operation_id)
            try:
                stage = CRMStageDefinition.create(
                    code, name, uow.stage_definitions.max_sequence() + 1,
                    probability_default=int(probability_default), is_won_stage=is_won_stage,
                    is_lost_stage=is_lost_stage, min_activities=int(min_activities),
                    required_fields=tuple(required_fields))
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.stage_definitions.save(stage)
            self._audit(uow, actor_user_id, stage, "alta de etapa", operation_id)
        return CRMResult.ok("Etapa creada", entity_id=stage.id, operation_id=operation_id)


class UpdateStageDefinitionUseCase(_Base):
    def execute(self, connection, *, actor_user_id: str, stage_id: str, operation_id: str,
                name: str | None = None, probability_default: int | None = None,
                min_activities: int | None = None,
                required_fields: tuple[str, ...] | None = None) -> CRMResult:
        denied = self._deny(actor_user_id, operation_id)
        if denied:
            return denied
        with CRMUnitOfWork(connection) as uow:
            stage = uow.stage_definitions.get(stage_id)
            if stage is None:
                return CRMResult.fail("La etapa no existe.", "NOT_FOUND",
                                      operation_id=operation_id)
            if name is not None:
                if not name.strip():
                    return CRMResult.fail("El nombre es obligatorio.", "VALIDATION",
                                          operation_id=operation_id)
                stage.name = name.strip()
            if probability_default is not None:
                stage.probability_default = int(probability_default)
            if min_activities is not None:
                stage.min_activities = int(min_activities)
            if required_fields is not None:
                stage.required_fields = tuple(required_fields)
            problem = _check_bounds(stage.probability_default, stage.min_activities)
            if problem:
                return CRMResult.fail(problem, "VALIDATION", operation_id=operation_id)
            stage.updated_at = _now()
            uow.stage_definitions.update(stage)
            self._audit(uow, actor_user_id, stage, "edición de etapa", operation_id)
        return CRMResult.ok("Etapa actualizada", entity_id=stage_id, operation_id=operation_id)


class MoveStageDefinitionUseCase(_Base):
    """Sube (``direction < 0``) o baja una etapa un lugar."""

    def execute(self, connection, *, actor_user_id: str, stage_id: str, direction: int,
                operation_id: str) -> CRMResult:
        denied = self._deny(actor_user_id, operation_id)
        if denied:
            return denied
        with CRMUnitOfWork(connection) as uow:
            ordered = uow.stage_definitions.list_active_ordered()
            index = next((i for i, s in enumerate(ordered) if s.id == stage_id), None)
            if index is None:
                return CRMResult.fail("La etapa no existe o está retirada.", "NOT_FOUND",
                                      operation_id=operation_id)
            other = index + (1 if direction > 0 else -1)
            if not 0 <= other < len(ordered):
                return CRMResult.fail("La etapa ya está en el extremo.", "VALIDATION",
                                      operation_id=operation_id)
            a, b = ordered[index], ordered[other]
            a.sequence_order, b.sequence_order = b.sequence_order, a.sequence_order
            a.updated_at = b.updated_at = _now()
            uow.stage_definitions.update(a)
            uow.stage_definitions.update(b)
            self._audit(uow, actor_user_id, a, "cambio de orden", operation_id)
        return CRMResult.ok("Orden actualizado", entity_id=stage_id, operation_id=operation_id)


class DeactivateStageDefinitionUseCase(_Base):
    def execute(self, connection, *, actor_user_id: str, stage_id: str, operation_id: str,
                reason: str = "") -> CRMResult:
        denied = self._deny(actor_user_id, operation_id)
        if denied:
            return denied
        with CRMUnitOfWork(connection) as uow:
            stage = uow.stage_definitions.get(stage_id)
            if stage is None or not stage.active:
                return CRMResult.fail("La etapa no existe o ya está retirada.", "NOT_FOUND",
                                      operation_id=operation_id)
            in_use = [o for o in uow.opportunities.list_by_stage(stage_id, limit=500)
                      if o.status.value in ("OPEN", "ON_HOLD")]
            if in_use:
                return CRMResult.fail(
                    f"Hay {len(in_use)} oportunidad(es) abierta(s) en esta etapa; "
                    "muévelas antes de retirarla.", "STAGE_IN_USE", operation_id=operation_id)
            stage.deactivate()
            others = [s for s in uow.stage_definitions.list_all_ordered() if s.id != stage_id]
            problem = _terminal_guard(others + [stage])
            if problem:
                return CRMResult.fail(problem, "VALIDATION", operation_id=operation_id)
            uow.stage_definitions.update(stage)
            self._audit(uow, actor_user_id, stage, reason or "retiro de etapa", operation_id)
        return CRMResult.ok("Etapa retirada", entity_id=stage_id, operation_id=operation_id)
