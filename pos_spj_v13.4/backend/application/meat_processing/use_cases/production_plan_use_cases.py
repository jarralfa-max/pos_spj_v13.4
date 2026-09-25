"""Plan de producción (§11; decisiones del usuario, 2026-09-25).

- Un plan por sucursal y DÍA. Crearlo dos veces para el mismo día devuelve el
  que ya existe.
- Sus líneas dicen qué producto se necesita y CÓMO atenderlo (proceso y
  producto objetivo de la orden). Vienen de captura manual, de la reposición de
  Inventario o del pronóstico de BI; el planeador las confirma.
- Flujo: borrador → generado → en revisión → aprobado (lo aprueba OTRO
  usuario) → convertido. Cancelable antes de convertir todo.
- Convertir una línea crea la orden de procesamiento (con folio) y la deja
  APROBADA por quien aprobó el plan; quien aprobó el plan no la convierte
  (segregación). Es reanudable: repetir la conversión con la misma operación
  no duplica la orden ni la conversión.
- El plan no mueve inventario.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.domain.meat_processing.entities.production_plan import ProductionPlan
from backend.domain.meat_processing.entities.production_plan_line import ProductionPlanLine
from backend.domain.meat_processing.enums import (
    PlanSourceType,
    ProcessingOrderStatus,
    ProcessType,
    ProductionPlanStatus,
)
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingPermissionDeniedError,
    MeatProcessingScopeError,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid

PLAN_SOURCE_DOCUMENT = "PRODUCTION_PLAN"


def _branch_fail(context: MeatProcessingExecutionContext | None, branch_id: str,
                 operation_id: str) -> MeatProcessingResult | None:
    if context is None:
        return None
    try:
        context.enforce_branch(branch_id)
    except MeatProcessingScopeError as exc:
        return _fail(exc, operation_id)
    return None


def _event(uow, name, *, operation_id, plan, actor, **extra) -> None:
    payload = build_meat_processing_event(
        name, operation_id=operation_id, entity_id=plan.id, branch_id=plan.branch_id,
        warehouse_id=None, user_id=actor, planning_period=plan.planning_period, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


def _audit(uow, plan, action, *, actor, operation_id, after=None) -> None:
    uow.audit.record(entity_type="ProductionPlan", entity_id=plan.id, action=action,
                     user_id=actor, operation_id=operation_id, branch_id=plan.branch_id,
                     after_json=json.dumps(after) if after is not None else None)


def planning_day(value) -> str:
    """El periodo de un plan es un DÍA (AAAA-MM-DD)."""
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value).strip()[:10]).isoformat()


class CreateProductionPlanUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, branch_id: str, planning_date, operation_id: str,
                actor_user_id: str,
                context: MeatProcessingExecutionContext | None = None) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.PLAN_CREATE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        denied = _branch_fail(context, branch_id, operation_id)
        if denied is not None:
            return denied
        try:
            dia = planning_day(planning_date)
        except ValueError:
            return MeatProcessingResult.fail("La fecha del plan no es válida",
                                             "INVALID_PLANNING_DATE", operation_id=operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                existente = uow.production_plans.get_for_day(branch_id, dia)
                if existente is not None:
                    return MeatProcessingResult.ok(
                        "Ya hay un plan para ese día", entity_id=existente.id,
                        operation_id=operation_id, already_processed=True)
                plan = ProductionPlan(id=new_uuid(), operation_id=operation_id,
                                      branch_id=branch_id, planning_period=dia,
                                      created_by_user_id=actor_user_id)
                uow.production_plans.save(plan)
                _audit(uow, plan, "CREATED", actor=actor_user_id, operation_id=operation_id)
                _event(uow, MeatProcessingEvents.PRODUCTION_PLAN_CREATED,
                       operation_id=operation_id, plan=plan, actor=actor_user_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(f"Plan del {dia} creado", entity_id=plan.id,
                                       operation_id=operation_id)


class AddProductionPlanLineUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, plan_id: str, product_id: str, process_type,
                target_product_id: str | None, planned_weight, operation_id: str,
                actor_user_id: str, planned_quantity=Decimal("0"),
                source_type=PlanSourceType.MANUAL, source_reference_id: str | None = None,
                required_date=None, priority: int = 0,
                context: MeatProcessingExecutionContext | None = None) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.PLAN_EDIT)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                plan = uow.production_plans.get(plan_id)
                if plan is None:
                    return MeatProcessingResult.fail("Plan no encontrado", "PLAN_NOT_FOUND",
                                                     operation_id=operation_id)
                denied = _branch_fail(context, plan.branch_id, operation_id)
                if denied is not None:
                    return denied
                proceso = ProcessType(getattr(process_type, "value", process_type))
                linea = ProductionPlanLine(
                    id=new_uuid(), product_id=product_id,
                    source_type=PlanSourceType(str(getattr(source_type, "value", source_type))),
                    planned_quantity=Decimal(str(planned_quantity or 0)),
                    planned_weight=Decimal(str(planned_weight or 0)),
                    source_reference_id=source_reference_id, required_date=required_date,
                    priority=int(priority or 0), process_type=proceso,
                    target_product_id=target_product_id or product_id)
                plan.add_line(linea)
                uow.production_plans.save(plan)
                _audit(uow, plan, "LINE_ADDED", actor=actor_user_id, operation_id=operation_id,
                       after={"line_id": linea.id, "product_id": product_id,
                              "source_type": linea.source_type.value})
        except (MeatProcessingError, ValueError) as exc:
            return _fail(exc, operation_id) if isinstance(exc, MeatProcessingError) else \
                MeatProcessingResult.fail(str(exc), "INVALID_LINE", operation_id=operation_id)
        return MeatProcessingResult.ok("Línea agregada al plan", entity_id=linea.id,
                                       operation_id=operation_id)


class RemoveProductionPlanLineUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, plan_id: str, line_id: str, operation_id: str,
                actor_user_id: str,
                context: MeatProcessingExecutionContext | None = None) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.PLAN_EDIT)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                plan = uow.production_plans.get(plan_id)
                if plan is None:
                    return MeatProcessingResult.fail("Plan no encontrado", "PLAN_NOT_FOUND",
                                                     operation_id=operation_id)
                denied = _branch_fail(context, plan.branch_id, operation_id)
                if denied is not None:
                    return denied
                plan.remove_line(line_id)
                uow.production_plans.save(plan)
                _audit(uow, plan, "LINE_REMOVED", actor=actor_user_id,
                       operation_id=operation_id, after={"line_id": line_id})
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok("Línea quitada del plan", entity_id=plan_id,
                                       operation_id=operation_id)


def _transition(connection, *, plan_id, operation_id, actor_user_id, context, action,
                message, apply, event=None) -> MeatProcessingResult:
    """Cambio de estado del plan: cargar, validar alcance, aplicar la regla del
    dominio, guardar, auditar y (si aplica) publicar. El permiso lo exige cada
    caso de uso ANTES de llamar aquí."""
    try:
        with MeatProcessingUnitOfWork(connection) as uow:
            plan = uow.production_plans.get(plan_id)
            if plan is None:
                return MeatProcessingResult.fail("Plan no encontrado", "PLAN_NOT_FOUND",
                                                 operation_id=operation_id)
            denied = _branch_fail(context, plan.branch_id, operation_id)
            if denied is not None:
                return denied
            apply(plan)
            uow.production_plans.save(plan)
            _audit(uow, plan, action, actor=actor_user_id, operation_id=operation_id)
            if event:
                _event(uow, event, operation_id=operation_id, plan=plan, actor=actor_user_id)
    except MeatProcessingError as exc:
        return _fail(exc, operation_id)
    return MeatProcessingResult.ok(message, entity_id=plan.id, operation_id=operation_id,
                                   status=plan.status.value)


class GenerateProductionPlanUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, plan_id: str, operation_id: str, actor_user_id: str,
                context: MeatProcessingExecutionContext | None = None) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.PLAN_EDIT)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        return _transition(connection, plan_id=plan_id, operation_id=operation_id,
                           actor_user_id=actor_user_id, context=context, action="GENERATED",
                           message="Plan generado", apply=lambda plan: plan.generate())


class SubmitProductionPlanUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, plan_id: str, operation_id: str, actor_user_id: str,
                context: MeatProcessingExecutionContext | None = None) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.PLAN_EDIT)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        return _transition(connection, plan_id=plan_id, operation_id=operation_id,
                           actor_user_id=actor_user_id, context=context, action="SUBMITTED",
                           message="Plan enviado a revisión",
                           apply=lambda plan: plan.submit_for_review())


class ApproveProductionPlanUseCase:
    """Lo aprueba OTRO usuario (segregación en el dominio)."""

    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, plan_id: str, operation_id: str, actor_user_id: str,
                context: MeatProcessingExecutionContext | None = None) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.PLAN_APPROVE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        return _transition(connection, plan_id=plan_id, operation_id=operation_id,
                           actor_user_id=actor_user_id, context=context, action="APPROVED",
                           message="Plan aprobado",
                           event=MeatProcessingEvents.PRODUCTION_PLAN_APPROVED,
                           apply=lambda plan: plan.approve(actor_user_id=actor_user_id))


class CancelProductionPlanUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, plan_id: str, operation_id: str, actor_user_id: str,
                context: MeatProcessingExecutionContext | None = None) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.PLAN_CANCEL)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        return _transition(connection, plan_id=plan_id, operation_id=operation_id,
                           actor_user_id=actor_user_id, context=context, action="CANCELLED",
                           message="Plan cancelado",
                           event=MeatProcessingEvents.PRODUCTION_PLAN_CANCELLED,
                           apply=lambda plan: plan.cancel())


class ConvertProductionPlanLineUseCase:
    """Convierte (una parte de) una línea de un plan APROBADO en una orden de
    procesamiento que nace APROBADA por quien aprobó el plan."""

    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None, *,
                 folio_port=None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()
        self._folio = folio_port

    def execute(self, connection, *, plan_id: str, line_id: str, warehouse_id: str,
                operation_id: str, actor_user_id: str, planned_weight=None,
                planned_quantity=None,
                context: MeatProcessingExecutionContext | None = None) -> MeatProcessingResult:
        from backend.application.meat_processing.use_cases.processing_order_use_cases import (
            CreateProcessingOrderUseCase,
        )

        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_CREATE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        uow = MeatProcessingUnitOfWork(connection)
        plan = uow.production_plans.get(plan_id)
        if plan is None:
            return MeatProcessingResult.fail("Plan no encontrado", "PLAN_NOT_FOUND",
                                             operation_id=operation_id)
        denied = _branch_fail(context, plan.branch_id, operation_id)
        if denied is not None:
            return denied
        linea = next((l for l in plan.lines if l.id == line_id), None)
        if linea is None:
            return MeatProcessingResult.fail("Línea no encontrada en el plan",
                                             "PLAN_LINE_NOT_FOUND", operation_id=operation_id)
        if plan.status not in (ProductionPlanStatus.APPROVED,
                               ProductionPlanStatus.PARTIALLY_CONVERTED):
            return MeatProcessingResult.fail(
                "Sólo se convierten líneas de un plan aprobado", "PLAN_NOT_APPROVED",
                operation_id=operation_id)
        if not linea.is_convertible:
            return MeatProcessingResult.fail(
                "La línea no indica el proceso ni el producto objetivo de la orden",
                "PLAN_LINE_INCOMPLETE", operation_id=operation_id)
        if actor_user_id == plan.approved_by_user_id:
            return MeatProcessingResult.fail(
                "Quien aprobó el plan no convierte sus líneas: la orden nace aprobada por "
                "esa aprobación, así que la convierte otro usuario.",
                "SEGREGATION_OF_DUTIES", operation_id=operation_id)
        peso = Decimal(str(planned_weight)) if planned_weight not in (None, "") else \
            linea.planned_weight - linea.converted_weight
        cantidad = Decimal(str(planned_quantity)) if planned_quantity not in (None, "") else \
            linea.planned_quantity - linea.converted_quantity
        if peso <= 0 and cantidad <= 0:
            return MeatProcessingResult.fail("La línea ya está convertida por completo",
                                             "PLAN_LINE_CONVERTED", operation_id=operation_id)

        creada = CreateProcessingOrderUseCase(self._auth, folio_port=self._folio).execute(
            connection, operation_id=operation_id, branch_id=plan.branch_id,
            warehouse_id=warehouse_id, process_type=linea.process_type,
            target_product_id=linea.target_product_id, planned_quantity=max(cantidad, 0),
            planned_weight=max(peso, 0), actor_user_id=actor_user_id,
            source_type=PLAN_SOURCE_DOCUMENT, source_reference_id=linea.id, context=context)
        if not creada.success:
            return creada
        orden_id = creada.entity_id
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                orden = uow.orders.get(orden_id)
                if orden.status is ProcessingOrderStatus.PENDING_APPROVAL:
                    orden.approve(actor_user_id=plan.approved_by_user_id)
                    uow.orders.save(orden)
                    uow.audit.record(
                        entity_type="ProcessingOrder", entity_id=orden.id,
                        action="APPROVED_BY_PLAN", user_id=plan.approved_by_user_id,
                        operation_id=operation_id, branch_id=orden.branch_id,
                        warehouse_id=orden.warehouse_id, processing_order_id=orden.id,
                        after_json=json.dumps({"plan_id": plan.id, "line_id": linea.id}))
                    aprobada = build_meat_processing_event(
                        MeatProcessingEvents.PROCESSING_ORDER_APPROVED,
                        operation_id=operation_id, entity_id=orden.id,
                        branch_id=orden.branch_id, warehouse_id=orden.warehouse_id,
                        user_id=plan.approved_by_user_id, production_plan_id=plan.id)
                    uow.outbox.enqueue(event_id=aprobada["event_id"],
                                       event_name=MeatProcessingEvents.PROCESSING_ORDER_APPROVED,
                                       payload_json=json.dumps(aprobada),
                                       operation_id=operation_id)
                fresco = uow.production_plans.get(plan.id)
                linea_fresca = next(l for l in fresco.lines if l.id == linea.id)
                if orden.id not in linea_fresca.converted_processing_order_ids:
                    fresco.convert_line(linea.id, processing_order_id=orden.id,
                                        converted_quantity=max(cantidad, 0),
                                        converted_weight=max(peso, 0))
                    uow.production_plans.save(fresco)
                    _audit(uow, fresco, "LINE_CONVERTED", actor=actor_user_id,
                           operation_id=operation_id,
                           after={"line_id": linea.id, "processing_order_id": orden.id})
                    _event(uow, MeatProcessingEvents.PRODUCTION_PLAN_LINE_CONVERTED,
                           operation_id=operation_id, plan=fresco, actor=actor_user_id,
                           line_id=linea.id, processing_order_id=orden.id)
                    if fresco.status is ProductionPlanStatus.CONVERTED:
                        _event(uow, MeatProcessingEvents.PRODUCTION_PLAN_CONVERTED,
                               operation_id=operation_id, plan=fresco, actor=actor_user_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            f"Orden {orden.folio or ''} creada y aprobada".replace("  ", " "),
            entity_id=orden.id, operation_id=operation_id, folio=orden.folio)
