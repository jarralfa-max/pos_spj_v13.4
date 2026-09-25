"""Preparación de una orden (§15/§16): congelar la definición, derivar los
requerimientos y RESERVAR existencia real en Inventario.

UNA sola ruta: `PrepareProcessingOrderUseCase`.

1. Congela la definición productiva (`ProcessingRecipeSnapshot`) que Productos
   tiene activa, si todavía no está congelada, y exige lo que el proceso
   necesita (`ProcessingMasterDataRequirementPolicy`). Sin definición
   obligatoria, la orden no avanza.
2. Deriva los requerimientos de material de ESA definición y del peso
   planeado. No hay alta manual de requerimientos: sería otra ruta que se
   saltaría la definición de Productos.
3. Pide a Inventario la reserva de cada requerimiento. Inventario elige lotes y
   ubicaciones (FEFO/FIFO/manual) y retiene los saldos exactos; aquí se guarda
   la reserva, el lote y la ubicación que devolvió. Procesamiento ya no lleva
   una reserva propia paralela.
4. Sólo si TODO quedó reservado la orden pasa a READY. Si falta existencia se
   queda en MATERIALS_PENDING con lo que falta; nunca se reserva a medias ni
   se inventa existencia.

Reintentar es seguro: la definición no se vuelve a congelar, los requerimientos
no se duplican y cada reserva usa el `operation_id` guardado en la bitácora.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.ports import (
    MaterialReservationPort,
    NullMaterialReservationPort,
    NullRecipeSnapshotPort,
    RecipeSnapshotPort,
)
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.domain.meat_processing.entities.material_requirement import MaterialRequirement
from backend.domain.meat_processing.entities.operator_assignment import OperatorAssignment
from backend.domain.meat_processing.enums import (
    MaterialRequirementStatus,
    OperatorRole,
    ProcessingOrderStatus,
)
from backend.domain.meat_processing.events import MeatProcessingEvents, build_meat_processing_event
from backend.domain.meat_processing.exceptions import (
    MeatProcessingError,
    MeatProcessingPermissionDeniedError,
)
from backend.domain.meat_processing.policies.master_data_requirement_policy import (
    ProcessingMasterDataRequirementPolicy,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid

_PREPARABLE = (ProcessingOrderStatus.APPROVED, ProcessingOrderStatus.MATERIALS_PENDING)
RESERVE_STEP = "RESERVE_MATERIAL"


def freeze_processing_definition(uow, order, *, snapshot_port: RecipeSnapshotPort,
                                 policy: ProcessingMasterDataRequirementPolicy,
                                 actor_user_id: str):
    """Congela la definición de la orden, o devuelve la ya congelada.

    Devuelve `(snapshot, None)` o `(None, mensaje)` si Productos no tiene lo
    que el proceso exige. Es el ÚNICO lugar que congela: preparar lo llama y
    liberar exige que ya exista."""
    congelado = uow.recipe_snapshots.get_by_order(order.id)
    if congelado is not None:
        revision = policy.check(order.process_type, congelado)
        return (congelado, None) if revision.ok else (None, revision.message())
    resuelto = snapshot_port.resolve(target_product_id=order.target_product_id,
                                     process_type=order.process_type)
    revision = policy.check(order.process_type, resuelto)
    if not revision.ok:
        return None, revision.message()
    congelado = resuelto.frozen_for(processing_order_id=order.id,
                                    captured_by_user_id=actor_user_id,
                                    operation_id=new_uuid())
    uow.recipe_snapshots.add(congelado)
    order.apply_recipe_snapshot(
        recipe_version_id=congelado.recipe_version_id,
        cutting_scheme_version_id=congelado.cutting_scheme_version_id,
        yield_profile_version_id=congelado.yield_profile_version_id)
    uow.orders.save(order)
    uow.audit.record(
        entity_type="ProcessingOrder", entity_id=order.id, action="RECIPE_SNAPSHOT_CAPTURED",
        user_id=actor_user_id, operation_id=congelado.operation_id,
        after_json=json.dumps({
            "snapshot_id": congelado.id, "effective_version": congelado.effective_version,
            "recipe_version_id": congelado.recipe_version_id,
            "cutting_scheme_version_id": congelado.cutting_scheme_version_id,
            "yield_profile_version_id": congelado.yield_profile_version_id,
            "inputs": len(congelado.inputs), "outputs": len(congelado.outputs)}),
        branch_id=order.branch_id, warehouse_id=order.warehouse_id,
        processing_order_id=order.id)
    return congelado, None


class PrepareProcessingOrderUseCase:
    def __init__(
        self,
        authorization: MeatProcessingAuthorizationPolicy | None = None,
        *,
        recipe_snapshot_port: RecipeSnapshotPort | None = None,
        reservation_port_factory=None,
        master_data_policy: ProcessingMasterDataRequirementPolicy | None = None,
    ) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()
        self._snapshots = recipe_snapshot_port or NullRecipeSnapshotPort()
        #: (orden, actor) → MaterialReservationPort. Sin fábrica no hay reserva.
        self._reservations = reservation_port_factory or (
            lambda order, actor: NullMaterialReservationPort())
        self._policy = master_data_policy or ProcessingMasterDataRequirementPolicy()

    def execute(self, connection, *, order_id: str, operation_id: str, actor_user_id: str,
                context: MeatProcessingExecutionContext | None = None) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.MATERIAL_ASSIGN)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)

        # ── 1 y 2: definición congelada y requerimientos, en una transacción ──
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                order = uow.orders.get(order_id)
                if order is None:
                    return MeatProcessingResult.fail(
                        "Orden no encontrada", "ORDER_NOT_FOUND", operation_id=operation_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                if order.status is ProcessingOrderStatus.READY:
                    return MeatProcessingResult.ok(
                        "Orden ya preparada (idempotente)", entity_id=order.id,
                        operation_id=operation_id, already_processed=True, ready=True)
                if order.status not in _PREPARABLE:
                    return MeatProcessingResult.fail(
                        f"Sólo se prepara una orden aprobada (está {order.status.value}).",
                        "INVALID_STATE", operation_id=operation_id)
                snapshot, faltante = freeze_processing_definition(
                    uow, order, snapshot_port=self._snapshots, policy=self._policy,
                    actor_user_id=actor_user_id)
                if snapshot is None:
                    return MeatProcessingResult.fail(faltante, "MASTER_DATA_MISSING",
                                                     operation_id=operation_id)
                if not uow.material_requirements.list_by_order(order.id):
                    pesos = snapshot.required_input_weight(Decimal(str(order.planned_weight)))
                    for entrada in snapshot.inputs:
                        peso = pesos[entrada.product_id].quantize(Decimal("0.001"))
                        uow.material_requirements.save(MaterialRequirement(
                            id=new_uuid(), operation_id=new_uuid(),
                            processing_order_id=order.id, product_id=entrada.product_id,
                            required_weight=peso, unit=entrada.unit_id or "kg",
                            substitution_allowed=bool(snapshot.substitutions),
                            lot_required=entrada.lot_controlled))
                if order.status is ProcessingOrderStatus.APPROVED:
                    order.mark_materials_pending()
                    uow.orders.save(order)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)

        # ── 3: reservas reales, una por requerimiento pendiente ──────────────
        puerto: MaterialReservationPort = self._reservations(order, actor_user_id)
        faltantes = []
        requerimientos = MeatProcessingUnitOfWork(connection).material_requirements.list_by_order(
            order.id)
        for req in requerimientos:
            if req.status is not MaterialRequirementStatus.REQUIRED:
                continue
            with MeatProcessingUnitOfWork(connection) as uow:
                paso = uow.execution_steps.begin(order.id, RESERVE_STEP, req.id)
            resultado = puerto.reserve(
                operation_id=paso.operation_id, material_requirement_id=req.id,
                product_id=req.product_id, branch_id=order.branch_id,
                warehouse_id=order.warehouse_id, quantity=req.required_weight,
                lot_required=req.lot_required)
            try:
                with MeatProcessingUnitOfWork(connection) as uow:
                    if not resultado.ok:
                        uow.execution_steps.fail(paso, resultado.error or "sin reserva")
                        faltantes.append({
                            "product_id": req.product_id, "required": str(req.required_weight),
                            "available": (None if resultado.available is None
                                          else str(resultado.available)),
                            "message": resultado.error})
                        continue
                    total = Decimal("0")
                    for linea in resultado.lines:
                        uow.requirement_allocations.add(
                            material_requirement_id=req.id, processing_order_id=order.id,
                            product_id=req.product_id,
                            inventory_reservation_id=linea.reservation_id,
                            lot_id=linea.lot_id, location_id=linea.location_id,
                            quantity=linea.quantity)
                        total += linea.quantity
                    fresco = uow.material_requirements.get(req.id)
                    fresco.reserve(weight=total)
                    fresco.allocate(weight=total)
                    uow.material_requirements.save(fresco)
                    uow.execution_steps.complete(paso, ",".join(
                        l.reservation_id for l in resultado.lines))
                    evento = build_meat_processing_event(
                        MeatProcessingEvents.PROCESSING_MATERIAL_RESERVED,
                        operation_id=paso.operation_id, entity_id=req.id,
                        branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                        user_id=actor_user_id, correlation_id=operation_id,
                        inventory_reservation_ids=[l.reservation_id for l in resultado.lines])
                    uow.outbox.enqueue(
                        event_id=evento["event_id"],
                        event_name=MeatProcessingEvents.PROCESSING_MATERIAL_RESERVED,
                        payload_json=json.dumps(evento), operation_id=paso.operation_id)
            except MeatProcessingError as exc:
                return _fail(exc, operation_id)

        # ── 4: READY sólo con todo reservado ─────────────────────────────────
        if faltantes:
            return MeatProcessingResult.ok(
                "Faltan insumos por reservar: la orden sigue esperando materiales.",
                entity_id=order.id, operation_id=operation_id, ready=False,
                shortages=faltantes)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                fresca = uow.orders.get(order.id)
                pendientes = [r.id for r in uow.material_requirements.list_by_order(order.id)
                              if r.status is not MaterialRequirementStatus.ALLOCATED
                              or not uow.requirement_allocations.list_by_requirement(r.id)]
                if pendientes:
                    return MeatProcessingResult.fail(
                        "Hay requerimientos sin reserva real de Inventario",
                        "MATERIALS_NOT_READY", operation_id=operation_id,
                        requirement_ids=pendientes)
                fresca.mark_ready()
                uow.orders.save(fresca)
                uow.audit.record(
                    entity_type="ProcessingOrder", entity_id=fresca.id, action="PREPARED",
                    user_id=actor_user_id, operation_id=operation_id,
                    branch_id=fresca.branch_id, warehouse_id=fresca.warehouse_id,
                    processing_order_id=fresca.id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Orden preparada: insumos reservados en Inventario", entity_id=order.id,
            operation_id=operation_id, ready=True)


class AssignOperatorUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, order_id: str, operation_id: str, user_id: str,
        role_type: OperatorRole, actor_user_id: str, work_center_id: str | None = None,
        context: MeatProcessingExecutionContext | None = None,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.OPERATOR_ASSIGN)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                order = uow.orders.get(order_id)
                if order is None:
                    return MeatProcessingResult.fail(
                        "Orden no encontrada", "ORDER_NOT_FOUND", operation_id=operation_id)
                denied = _scope_fail(context, order.branch_id, order.warehouse_id, operation_id)
                if denied is not None:
                    return denied
                assignment = OperatorAssignment(
                    id=new_uuid(), operation_id=operation_id, processing_order_id=order_id,
                    user_id=user_id, role_type=role_type, work_center_id=work_center_id)
                uow.operator_assignments.save(assignment)
                uow.audit.record(
                    entity_type="OperatorAssignment", entity_id=assignment.id,
                    action="ASSIGNED", user_id=actor_user_id, operation_id=operation_id,
                    branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    processing_order_id=order_id)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Operario asignado", entity_id=assignment.id, operation_id=operation_id)


class ReleaseOperatorAssignmentUseCase:
    def __init__(self, authorization: MeatProcessingAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def execute(
        self, connection, *, assignment_id: str, operation_id: str, actor_user_id: str,
    ) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.OPERATOR_RELEASE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with MeatProcessingUnitOfWork(connection) as uow:
                assignment = uow.operator_assignments.get(assignment_id)
                if assignment is None:
                    return MeatProcessingResult.fail(
                        "Asignación no encontrada", "ASSIGNMENT_NOT_FOUND",
                        operation_id=operation_id)
                if not assignment.is_active:
                    return MeatProcessingResult.ok(
                        "Asignación ya liberada (idempotente)", entity_id=assignment.id,
                        operation_id=operation_id, already_processed=True)
                assignment.release()
                uow.operator_assignments.save(assignment)
        except MeatProcessingError as exc:
            return _fail(exc, operation_id)
        return MeatProcessingResult.ok(
            "Operario liberado", entity_id=assignment.id, operation_id=operation_id)
