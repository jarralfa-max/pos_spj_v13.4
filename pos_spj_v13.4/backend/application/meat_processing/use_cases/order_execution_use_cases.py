"""Ejecutar una orden de procesamiento — UNA ejecución para todos los procesos.

QUÉ CAMBIÓ Y POR QUÉ
--------------------
La versión anterior sólo sabía despiezar, releía el esquema de corte de
Productos, podía autorizar existencia negativa, liberaba la calidad de sus
propios outputs y calculaba el costo repartido. Ahora:

- Lee EXCLUSIVAMENTE la definición congelada de la orden
  (`ProcessingRecipeSnapshot`). No importa repositorios de Productos.
- Lo que difiere entre procesos lo decide la estrategia de su FAMILIA
  (`processing_execution_strategy`), nunca la especie.
- Consume lo que Inventario RESERVÓ al preparar (lote y ubicación exactos). No
  hay consumo sin reserva ni existencia negativa.
- Un output sujeto a inspección entra retenido y se pide la inspección a
  Calidad. Procesamiento no libera calidad.
- No calcula costos: al cerrar pide el costeo a Costos y guarda su referencia.
- Es una ORQUESTACIÓN REANUDABLE: cada paso que toca otro contexto tiene su
  `operation_id` (UUIDv7) guardado en `processing_execution_steps` antes de la
  llamada; reintentar tras un fallo reutiliza ese `operation_id` y el contexto
  dueño no duplica nada (consumo, lote, output, enlace, merma, costeo, cierre).

Todo se valida antes de mutar: definición, reservas, estrategia, tolerancias y
autorización de la variación.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.ports import ExecutionPorts
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import StepFailed
from backend.application.meat_processing.yield_settings import (
    ToleranceScope,
    YieldToleranceResolver,
)
from backend.domain.meat_processing.enums import (
    ConsumptionStatus,
    OutputQualityStatus,
    OutputType,
    ProcessingOrderStatus,
    YieldStatus,
)
from backend.domain.meat_processing.policies.yield_reconciliation_policy import (
    YieldReconciliationPolicy,
)
from backend.domain.meat_processing.services.processing_execution_strategy import (
    strategy_for,
)
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.meat_processing.execution")

_Q = Decimal("0.001")
_OUT = {YieldStatus.OUT_OF_TOLERANCE, YieldStatus.CRITICAL}
_RESUMABLE = {ProcessingOrderStatus.RELEASED, ProcessingOrderStatus.IN_PROGRESS,
              ProcessingOrderStatus.PENDING_QUALITY, ProcessingOrderStatus.PENDING_RECONCILIATION,
              ProcessingOrderStatus.PARTIALLY_COMPLETED, ProcessingOrderStatus.COMPLETED}

# ── pasos de la orquestación ────────────────────────────────────────────────
STEP_PLAN_CONSUMPTION = "PLAN_CONSUMPTION"
STEP_CAPTURE_CONSUMPTION = "CAPTURE_CONSUMPTION"
STEP_CONSUME = "CONSUME"
STEP_RELEASE_UNUSED = "RELEASE_UNUSED_RESERVATION"
STEP_RECORD_OUTPUTS = "RECORD_OUTPUTS"
STEP_REGISTER_LOT = "REGISTER_OUTPUT_LOT"
STEP_POST_OUTPUT = "POST_OUTPUT"
STEP_LINK = "LINK_GENEALOGY"
STEP_REQUEST_QUALITY = "REQUEST_QUALITY"
STEP_COMPLETE = "COMPLETE"
STEP_LOSS_CASE = "REQUEST_LOSS_CASE"
STEP_APPROVE_YIELD = "APPROVE_YIELD"
STEP_CLOSE = "CLOSE"


class ExecuteProcessingOrderUseCase:
    def __init__(self, authorization, *, ports_factory, authorizer_authorization=None,
                 authorizer_checker=None) -> None:
        #: (connection, order, actor_user_id, variance_reason) → ExecutionPorts
        self._ports_factory = ports_factory
        self._auth = authorization
        self._authorizer_auth = authorizer_authorization or authorization
        self._authorizer_checker = authorizer_checker

    # ── entrada ────────────────────────────────────────────────────────────
    def execute(self, connection, *, order_id: str, outputs: list[dict],
                actor_user_id: str, operation_id: str, inputs: list[dict] | None = None,
                variance_authorizer_user_id: str | None = None,
                variance_reason: str | None = None, context=None) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_START)
        except Exception as exc:  # noqa: BLE001 — permiso denegado
            return MeatProcessingResult.fail(str(exc), "PERMISSION_DENIED",
                                             operation_id=operation_id)
        preparado = self._prepare(connection, order_id=order_id, inputs=inputs,
                                  outputs=outputs, operation_id=operation_id)
        if isinstance(preparado, MeatProcessingResult):
            return preparado
        if preparado["out_of_tolerance"]:
            fuera = ", ".join(f"{r.product_id} ({r.variance_pct}%)"
                              for r in preparado["rows"] if r.product_id in preparado["out"])
            fallo = self._check_authorizer(
                variance_authorizer_user_id, variance_reason, actor_user_id,
                MeatProcessingPermissions.YIELD_OVERRIDE, operation_id,
                code="YIELD_AUTHORIZATION_REQUIRED",
                needed=(f"Rendimiento fuera de tolerancia en: {fuera}. Otro usuario con "
                        "permiso debe autorizar la diferencia (se abre caso en Mermas)."))
            if fallo:
                return fallo
        ports: ExecutionPorts = self._ports_factory(connection, preparado["order"],
                                                    actor_user_id, variance_reason)
        # Costos decide si puede costear lo que se va a producir; se pregunta
        # ANTES de mover existencia (sin costo de entrada o sin base de reparto
        # no se consume nada).
        costeo = ports.costing.preflight(
            processing_order_id=preparado["order"].id,
            process_type=preparado["snapshot"].process_type,
            consumed=[(a.product_id, preparado["takes"][a.id], a.allocated_lot_id)
                      for a in preparado["allocations"] if preparado["takes"].get(a.id)],
            produced=[(r.product_id, r.output_type, r.actual_weight)
                      for r in preparado["rows"] if r.actual_weight > 0])
        if costeo is not None:
            codigo, mensaje = costeo
            return MeatProcessingResult.fail(f"Costos no podrá costear la orden: {mensaje}",
                                             codigo, operation_id=operation_id)
        return self._run(connection, preparado, ports, actor_user_id=actor_user_id,
                         operation_id=operation_id,
                         variance_authorizer=variance_authorizer_user_id,
                         variance_reason=variance_reason, context=context)

    # ── validación completa, sin mutar nada ─────────────────────────────────
    def _prepare(self, connection, *, order_id, inputs, outputs, operation_id):
        from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
            MeatProcessingUnitOfWork,
        )

        def fail(msg, code, **data):
            return MeatProcessingResult.fail(msg, code, operation_id=operation_id, **data)

        uow = MeatProcessingUnitOfWork(connection)
        order = uow.orders.get(order_id)
        if order is None:
            return fail("Orden no encontrada", "ORDER_NOT_FOUND")
        if order.status not in _RESUMABLE:
            return fail(f"La orden está {order.status.value}: sólo se ejecuta una orden "
                        "preparada y liberada.", "INVALID_STATE")
        snapshot = uow.recipe_snapshots.get_by_order(order.id)
        if snapshot is None:
            return fail("La orden no tiene su definición productiva congelada.",
                        "NO_DEFINITION")
        estrategia = strategy_for(snapshot)
        if estrategia is None:
            return fail("El proceso de la orden no tiene comportamiento productivo definido.",
                        "UNSUPPORTED_PROCESS")
        asignaciones = [a for a in uow.requirement_allocations.list_by_order(order.id)
                        if a.status != "RELEASED"]
        if not asignaciones:
            return fail("La orden no tiene insumos reservados en Inventario: prepárala.",
                        "NOT_PREPARED")
        reservado: dict[str, Decimal] = {}
        for a in asignaciones:
            reservado[a.product_id] = reservado.get(a.product_id, Decimal("0")) + a.quantity

        plan = uow.execution_steps.get(order.id, STEP_PLAN_CONSUMPTION, order.id)
        tomas: dict[str, Decimal] | None = None
        if plan is not None and plan.done:  # reanudación: el plan guardado manda
            tomas = {k: Decimal(v) for k, v in json.loads(plan.result_reference).items()}
            por_id = {a.id: a for a in asignaciones}
            consumido = {}
            for aid, toma in tomas.items():
                pid = por_id[aid].product_id if aid in por_id else None
                if pid:
                    consumido[pid] = consumido.get(pid, Decimal("0")) + toma
        elif inputs:
            consumido = {}
            for linea in inputs:
                pid = str(linea.get("product_id") or "")
                if snapshot.input_for(pid) is None:
                    return fail(f"{pid} no es insumo de la definición de la orden.",
                                "INVALID_INPUT")
                consumido[pid] = consumido.get(pid, Decimal("0")) + Decimal(
                    str(linea.get("weight") or 0))
            for pid, peso in consumido.items():
                if peso > reservado.get(pid, Decimal("0")):
                    return fail(
                        f"Se capturan {peso} kg de {pid} y sólo hay {reservado.get(pid, 0)} kg "
                        "reservados. Prepara de nuevo la orden para reservar más; no se "
                        "consume existencia sin reservar.", "EXCEEDS_RESERVATION")
        else:
            consumido = dict(reservado)

        previas = uow.outputs.list_by_order(order.id)
        if previas:
            reales: dict[str, Decimal] = {}
            for s in previas:
                reales[s.product_id] = reales.get(s.product_id, Decimal("0")) + s.weight
        else:
            reales = {}
            for linea in outputs or []:
                pid = str(linea.get("product_id") or "")
                reales[pid] = reales.get(pid, Decimal("0")) + Decimal(
                    str(linea.get("weight") or 0))
        problemas = estrategia.validate(snapshot, consumido, reales)
        if problemas:
            return fail(" ".join(problemas), "INVALID_EXECUTION", problems=problemas)

        total = sum(consumido.values(), Decimal("0"))
        filas = estrategia.results(snapshot, total, reales)
        resolver = YieldToleranceResolver(connection)
        tecnicos = snapshot.technical_parameters or {}

        def tolerancia(product_id):
            return resolver.resolve(ToleranceScope(
                product_id=product_id, process_type=snapshot.process_type.value,
                species_id=tecnicos.get("species_id"), category_id=tecnicos.get("category_id"),
                work_center_id=order.work_center_id,
                production_area_id=order.production_area_id, branch_id=order.branch_id),
                profile_tolerance_pct=snapshot.tolerance_pct).tolerances

        fuera = set()
        estados = {}
        for r in filas:
            salida = snapshot.output_for(r.product_id)
            if not salida.goes_to_stock or r.variance_pct is None:
                estados[r.product_id] = YieldStatus.WITHIN_TOLERANCE
                continue
            tol = tolerancia(r.product_id)
            estado = YieldReconciliationPolicy.classify(
                r.variance_pct, warning_pct=tol.warning_pct, tolerance_pct=tol.tolerance_pct,
                critical_pct=tol.critical_pct)
            estados[r.product_id] = estado
            if estado in _OUT:
                fuera.add(r.product_id)
        if tomas is None:
            tomas, restante = {}, dict(consumido)
            for a in asignaciones:
                toma = min(a.quantity, restante.get(a.product_id, Decimal("0")))
                restante[a.product_id] = restante.get(a.product_id, Decimal("0")) - toma
                tomas[a.id] = toma
        return {"order": order, "snapshot": snapshot, "strategy": estrategia,
                "allocations": asignaciones, "takes": tomas,
                "consumed": consumido, "reales": reales,
                "total_input": total, "rows": filas, "statuses": estados, "out": fuera,
                "out_of_tolerance": bool(fuera),
                "order_tolerance": tolerancia(snapshot.target_product_id)}

    def _check_authorizer(self, authorizer, reason, actor, permission, operation_id, *,
                          code, needed):
        if not authorizer:
            return MeatProcessingResult.fail(needed, code, operation_id=operation_id)
        if not (reason or "").strip():
            return MeatProcessingResult.fail("La autorización requiere un motivo.", code,
                                             operation_id=operation_id)
        if str(authorizer) == str(actor):
            return MeatProcessingResult.fail(
                "Quien autoriza debe ser otro usuario (no quien ejecuta la orden).",
                "SEGREGATION_OF_DUTIES", operation_id=operation_id)
        checker = self._authorizer_checker
        if checker is None or not checker.has_permission(authorizer, permission):
            return MeatProcessingResult.fail(
                f"El autorizador no tiene el permiso {permission}.", "PERMISSION_DENIED",
                operation_id=operation_id)
        return None

    # ── bitácora de pasos ───────────────────────────────────────────────────
    def _step(self, connection, oid: str, step: str, target: str, action) -> str | None:
        from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
            MeatProcessingUnitOfWork,
        )
        with MeatProcessingUnitOfWork(connection) as uow:
            paso = uow.execution_steps.begin(oid, step, target)
        if paso.done:
            return paso.result_reference
        try:
            referencia = action(paso.operation_id)
        except StepFailed as exc:
            with MeatProcessingUnitOfWork(connection) as uow:
                uow.execution_steps.fail(paso, exc.message)
            raise
        with MeatProcessingUnitOfWork(connection) as uow:
            uow.execution_steps.complete(paso, referencia)
        return referencia

    # ── mutación, paso a paso y reanudable ──────────────────────────────────
    def _run(self, connection, p, ports, *, actor_user_id, operation_id, variance_authorizer,
             variance_reason, context):
        from backend.application.meat_processing.use_cases.consumption_weighing_use_cases import (
            CaptureMaterialConsumptionUseCase,
            PostMaterialConsumptionUseCase,
        )
        from backend.application.meat_processing.use_cases.execution_use_cases import (
            CompleteProcessExecutionUseCase,
            StartProcessExecutionUseCase,
        )
        from backend.application.meat_processing.use_cases.output_use_cases import (
            PostProcessOutputUseCase,
            RecordProcessOutputsUseCase,
        )
        from backend.application.meat_processing.use_cases.processing_order_use_cases import (
            CloseProcessingOrderUseCase,
        )
        from backend.application.meat_processing.use_cases.quality_use_cases import (
            RequestQualityInspectionUseCase,
        )
        from backend.application.meat_processing.use_cases.yield_use_cases import (
            ApproveYieldReconciliationUseCase,
            RequestLossCaseForYieldVarianceUseCase,
        )
        from backend.infrastructure.db.repositories.meat_processing.output_results_repository import (
            ProcessingOutputResultsRepository,
        )
        from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
            MeatProcessingUnitOfWork,
        )

        order, snapshot = p["order"], p["snapshot"]
        oid = order.id
        auth = self._auth
        common = {"actor_user_id": actor_user_id, "context": context}

        def exigir(nombre, result, detalle=None):
            if not result.success and not result.data.get("already_processed"):
                raise StepFailed(nombre, result.message, result.error_code or
                                  "EXECUTION_STEP_FAILED", detalle)
            return result

        try:
            if MeatProcessingUnitOfWork(connection).orders.get(oid).status is \
                    ProcessingOrderStatus.RELEASED:
                exigir("iniciar", StartProcessExecutionUseCase(auth).execute(
                    connection, order_id=oid, operation_id=new_uuid(), **common))

            # 1. el plan de consumo se guarda ANTES de capturar: al reanudar se
            #    sigue el mismo plan aunque un fallo haya cortado a la mitad.
            self._step(connection, oid, STEP_PLAN_CONSUMPTION, oid, lambda op: json.dumps(
                {aid: str(toma) for aid, toma in p["takes"].items()}))

            # 2. por cada reserva: capturar y descontar lo que se usó (cumpliendo
            #    la reserva en Inventario), o soltarla si no se usó.
            for a in MeatProcessingUnitOfWork(connection).requirement_allocations.list_by_order(oid):
                if a.status == "RELEASED":
                    continue
                toma = p["takes"].get(a.id, Decimal("0"))
                if toma > 0:
                    def capturar(op, a=a, toma=toma):
                        fresca = next(x for x in MeatProcessingUnitOfWork(
                            connection).requirement_allocations.list_by_order(oid) if x.id == a.id)
                        if fresca.material_consumption_id:
                            return fresca.material_consumption_id
                        previa = next((c for c in MeatProcessingUnitOfWork(connection)
                                       .consumptions.list_by_order(oid) if c.operation_id == op),
                                      None)
                        if previa is not None:  # capturado, pero no quedó enlazado
                            with MeatProcessingUnitOfWork(connection) as w:
                                w.requirement_allocations.attach_consumption(a.id, previa.id)
                            return previa.id
                        r = exigir("capturar el consumo", CaptureMaterialConsumptionUseCase(
                            auth).execute(
                            connection, order_id=oid, operation_id=op, product_id=a.product_id,
                            warehouse_id=order.warehouse_id, planned_quantity=Decimal("0"),
                            planned_weight=a.quantity, actual_quantity=Decimal("0"),
                            actual_weight=toma, lot_id=a.allocated_lot_id,
                            location_id=a.allocated_location_id, unit="kg", **common))
                        with MeatProcessingUnitOfWork(connection) as w:
                            w.requirement_allocations.attach_consumption(a.id, r.entity_id)
                        return r.entity_id
                    consumo_id = self._step(connection, oid, STEP_CAPTURE_CONSUMPTION, a.id,
                                            capturar)

                    def consumir(op, consumo_id=consumo_id):
                        r = PostMaterialConsumptionUseCase(
                            auth, inventory_port=ports.consumption).execute(
                            connection, consumption_id=consumo_id, operation_id=op,
                            actor_user_id=actor_user_id, context=context)
                        exigir("descontar el insumo", r, ports.consumption.last_error)
                        return r.entity_id
                    self._step(connection, oid, STEP_CONSUME, a.id, consumir)
                elif a.status == "RESERVED":
                    def soltar(op, a=a):
                        if not ports.reservation.release(
                                operation_id=op, reservation_id=a.inventory_reservation_id,
                                reason="Reserva no usada en la ejecución"):
                            raise StepFailed("soltar la reserva no usada",
                                              ports.reservation.last_error or "sin respuesta")
                        with MeatProcessingUnitOfWork(connection) as w:
                            w.requirement_allocations.mark_released(a.id)
                        return a.inventory_reservation_id
                    self._step(connection, oid, STEP_RELEASE_UNUSED, a.id, soltar)

            # 3. registrar las salidas (+ conciliación de la orden)
            def registrar(op):
                principal = sum((r.expected_weight for r in p["rows"]
                                 if r.output_type == OutputType.MAIN_PRODUCT.value),
                                Decimal("0"))
                tol = p["order_tolerance"]
                exigir("registrar salidas", RecordProcessOutputsUseCase(auth).execute(
                    connection, order_id=oid, operation_id=op,
                    input_quantity=Decimal("0"), input_weight=p["total_input"],
                    expected_output_quantity=Decimal("0"), expected_output_weight=principal,
                    outputs=[{"product_id": pid, "output_type": snapshot.output_for(pid).output_type,
                              "weight": peso, "unit": "kg",
                              "quality_status": (OutputQualityStatus.PENDING_INSPECTION
                                                 if snapshot.output_for(pid).quality_gate
                                                 else OutputQualityStatus.NOT_REQUIRED)}
                             for pid, peso in p["reales"].items() if peso > 0],
                    warning_pct=tol.warning_pct, tolerance_pct=tol.tolerance_pct,
                    critical_pct=tol.critical_pct, **common))
                return op
            self._step(connection, oid, STEP_RECORD_OUTPUTS, oid, registrar)

            # 4. cada salida a existencia: lote, recepción, genealogía, calidad
            lotes_entrada = sorted({c.lot_id for c in MeatProcessingUnitOfWork(
                connection).consumptions.list_by_order(oid)
                if c.lot_id and c.status is ConsumptionStatus.POSTED})
            codigo = f"OP-{oid[-8:].upper()}-{datetime.now(timezone.utc):%Y%m%d}"
            for s in MeatProcessingUnitOfWork(connection).outputs.list_by_order(oid):
                if s.output_type.value in ("WASTE", "LOSS"):
                    continue
                retenido = s.quality_status is OutputQualityStatus.PENDING_INSPECTION \
                    or s.quality_status is OutputQualityStatus.QUARANTINED

                def lote(op, s=s, retenido=retenido):
                    try:
                        ubicacion = ports.output_location(s.product_id)
                    except Exception as exc:  # noqa: BLE001 — ubicación no configurada
                        raise StepFailed("resolver la ubicación de destino", str(exc),
                                          "LOCATION_NOT_CONFIGURED")
                    lote_id = ports.receipt.register_output_lot(
                        operation_id=op, product_id=s.product_id, lot_code=codigo,
                        quality_hold=retenido)
                    if lote_id is None:
                        raise StepFailed("registrar el lote de la salida",
                                          ports.receipt.last_error or "sin respuesta")
                    with MeatProcessingUnitOfWork(connection) as w:
                        fresco = w.outputs.get(s.id)
                        if fresco.inventory_operation_id is None:
                            fresco.place(lot_id=lote_id, location_id=ubicacion)
                            w.outputs.save(fresco)
                    return lote_id
                lote_id = self._step(connection, oid, STEP_REGISTER_LOT, s.id, lote)

                def recibir(op, s=s):
                    r = PostProcessOutputUseCase(auth, inventory_port=ports.receipt).execute(
                        connection, output_id=s.id, operation_id=op,
                        actor_user_id=actor_user_id, context=context)
                    exigir("recibir la salida", r, ports.receipt.last_error)
                    return r.entity_id
                self._step(connection, oid, STEP_POST_OUTPUT, s.id, recibir)

                for padre in lotes_entrada:
                    def enlazar(op, padre=padre, s=s, hijo=lote_id):
                        ref = ports.receipt.link_lot_genealogy(
                            operation_id=op, parent_lot_id=padre, child_lot_id=hijo,
                            product_id=s.product_id)
                        if ref is None:
                            raise StepFailed("enlazar la genealogía",
                                              ports.receipt.last_error or "sin respuesta")
                        return ref
                    # La clave del paso es el par de lotes (no es una identidad:
                    # la identidad de la operación es el UUIDv7 del paso).
                    self._step(connection, oid, STEP_LINK, f"{padre}>{lote_id}", enlazar)

                if retenido:
                    def pedir_calidad(op, s=s):
                        r = RequestQualityInspectionUseCase(
                            auth, quality_port=ports.quality).execute(
                            connection, output_id=s.id, operation_id=op,
                            actor_user_id=actor_user_id, context=context)
                        exigir("pedir la inspección a Calidad", r, ports.quality.last_error)
                        return r.data.get("inspection_request_id")
                    self._step(connection, oid, STEP_REQUEST_QUALITY, s.id, pedir_calidad)

            # 5. resultado por salida (sin costos: son de Costos)
            ProcessingOutputResultsRepository(connection).replace_for_order(oid, [{
                "product_id": r.product_id, "output_type": r.output_type,
                "input_product_id": snapshot.inputs[0].product_id,
                "input_weight": p["total_input"],
                "expected_weight": r.expected_weight, "actual_weight": r.actual_weight,
                "difference_weight": r.difference_weight,
                "expected_yield_pct": r.expected_yield_pct, "yield_pct": r.yield_pct,
                "variance_pct": r.variance_pct,
                "input_lot_id": lotes_entrada[0] if lotes_entrada else None,
                "output_lot_id": next((s.lot_id for s in MeatProcessingUnitOfWork(
                    connection).outputs.list_by_order(oid) if s.product_id == r.product_id),
                    None)} for r in p["rows"]])
            with MeatProcessingUnitOfWork(connection) as audit_uow:
                audit_uow.audit.record(
                    entity_type="ProcessingOrder", entity_id=oid, action="EXECUTED",
                    user_id=actor_user_id, operation_id=operation_id,
                    after_json=json.dumps({
                        "input_weight": str(p["total_input"]),
                        "definition": snapshot.effective_version,
                        "variance_authorized_by": (variance_authorizer
                                                   if p["out_of_tolerance"] else None),
                        "variance_reason": variance_reason if p["out_of_tolerance"] else None,
                    }), branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    processing_order_id=oid)

            # 6. completar, conciliar, merma, cerrar (con costeo de Costos)
            if MeatProcessingUnitOfWork(connection).orders.get(oid).status is not \
                    ProcessingOrderStatus.COMPLETED:
                self._step(connection, oid, STEP_COMPLETE, oid, lambda op: exigir(
                    "completar", CompleteProcessExecutionUseCase(auth).execute(
                        connection, order_id=oid, operation_id=op, **common)).entity_id)

            for conc in MeatProcessingUnitOfWork(connection).yield_reconciliations.list_by_order(oid):
                if conc.status is YieldStatus.APPROVED:
                    continue
                if conc.status in _OUT:
                    self._step(connection, oid, STEP_LOSS_CASE, conc.id, lambda op, c=conc: exigir(
                        "abrir el caso de merma", RequestLossCaseForYieldVarianceUseCase(
                            auth, loss_case_port=ports.losses).execute(
                            connection, reconciliation_id=c.id, operation_id=op,
                            actor_user_id=actor_user_id, context=context),
                        ports.losses.last_error).entity_id)
                aprobador, politica = ((variance_authorizer, self._authorizer_auth)
                                       if conc.status in _OUT and variance_authorizer
                                       else (actor_user_id, auth))
                self._step(connection, oid, STEP_APPROVE_YIELD, conc.id, lambda op, c=conc: exigir(
                    "aprobar el rendimiento", ApproveYieldReconciliationUseCase(politica).execute(
                        connection, reconciliation_id=c.id, operation_id=op,
                        actor_user_id=aprobador)).entity_id)

            def cerrar(op):
                r = CloseProcessingOrderUseCase(auth, cost_allocation_port=ports.costing).execute(
                    connection, order_id=oid, operation_id=op, **common)
                if not r.success:
                    raise StepFailed("cerrar", r.message, r.error_code or "CLOSE_FAILED",
                                      ports.costing.last_error)
                return r.data.get("cost_allocation_reference")
            referencia_costo = self._step(connection, oid, STEP_CLOSE, oid, cerrar)
        except StepFailed as exc:
            logger.warning("orden %s: falló '%s': %s", oid, exc.step, exc.message)
            detalle = f" ({exc.detail})" if exc.detail else ""
            return MeatProcessingResult.fail(
                f"No se pudo {exc.step}: {exc.message}{detalle}. Lo ya hecho quedó "
                "registrado; vuelve a ejecutar para continuar.", exc.code,
                operation_id=operation_id, step=exc.step)

        resultados = ProcessingOutputResultsRepository(connection).list_by_order(oid)
        return MeatProcessingResult.ok(
            "Orden ejecutada y cerrada", entity_id=oid, operation_id=operation_id,
            results=resultados, out_of_tolerance=p["out_of_tolerance"],
            cost_allocation_reference=referencia_costo)
