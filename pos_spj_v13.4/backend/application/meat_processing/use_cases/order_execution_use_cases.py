"""Ejecutar una orden de despiece de punta a punta (Fase 10, 2026-09-19).

QUÉ PASABA (medido con la sesión real)
--------------------------------------
De ~50 casos de uso de Cárnico, la pantalla conectaba 4 (crear, aprobar,
liberar, cerrar). No había forma de consumir la entrada, pesar las salidas ni
conciliar; los puertos a Inventario, Costos y Mermas eran nulos, así que
ninguna orden podía cerrarse jamás.

QUÉ HACE
--------
Orquesta los casos de uso EXISTENTES —no los reimplementa— en el orden del §14:
iniciar → consumir la entrada → registrar salidas (+ conciliación de la orden)
→ calidad → recibir salidas en Inventario con lote y costo repartido →
resultado por corte (§13) → completar → aprobar rendimiento (y caso de merma si
se sale de tolerancia) → cerrar (costo al promedio).

Decisiones del usuario:
- lo esperado por corte sale del ESQUEMA DE CORTE capturado al liberar;
- tolerancia GLOBAL configurable (aviso/tolerancia/crítico, %);
- costo repartido por VALOR DE VENTA RELATIVO;
- sin existencia de la entrada → autorización en caliente de otro usuario con
  `PRODUCCION.consumo.sobrescribir` + motivo; un corte fuera de tolerancia →
  autorización de otro usuario con `PRODUCCION.rendimiento.sobrescribir` + motivo.

TODO se valida antes de mutar (despiece, existencia, costo, precios, reparto,
autorizaciones). Y es REANUDABLE: cada paso mira lo que ya existe (consumo
publicado, salidas registradas, calidad, recepción, conciliación aprobada), así
que reintentar tras un fallo continúa donde se quedó en vez de duplicar.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from datetime import datetime, timezone

from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.yield_settings import YieldToleranceSettingsQueryService
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
from backend.domain.meat_processing.services.cost_allocation_service import (
    AllocationInput,
    CostAllocationError,
    RelativeSalesValueCostAllocation,
)
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.meat_processing.execution")

_Q = Decimal("0.001")
_PCT = Decimal("0.01")
_NO_STOCK = {"WASTE", "LOSS"}
_OUT = {YieldStatus.OUT_OF_TOLERANCE, YieldStatus.CRITICAL}
_RESUMABLE = {ProcessingOrderStatus.RELEASED, ProcessingOrderStatus.IN_PROGRESS,
              ProcessingOrderStatus.PENDING_QUALITY, ProcessingOrderStatus.PENDING_RECONCILIATION,
              ProcessingOrderStatus.PARTIALLY_COMPLETED, ProcessingOrderStatus.COMPLETED}


@dataclass(frozen=True)
class PlannedOutput:
    product_id: str
    output_type: str
    per_unit: Decimal          # kg de salida por kg de entrada (del despiece)
    expected_weight: Decimal   # para el peso planeado de la orden
    product_name: str = ""


class ProcessingOrderExecutionQueryService:
    """Lo que la pantalla necesita para capturar: entrada y salidas esperadas."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def plan(self, order_id: str) -> dict | None:
        from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
            MeatProcessingUnitOfWork,
        )
        from backend.infrastructure.db.repositories.products.cutting_scheme_repository import (
            CuttingSchemeRepository,
        )
        order = MeatProcessingUnitOfWork(self._conn).orders.get(order_id)
        if order is None:
            return None
        version = (CuttingSchemeRepository(self._conn).get_version(order.cutting_scheme_version_id)
                   if order.cutting_scheme_version_id else None)
        planeado = Decimal(str(order.planned_weight or 0))
        salidas = [] if version is None else [
            PlannedOutput(o.product_id, o.output_type.value, o.quantity,
                          (o.quantity * planeado).quantize(_Q),
                          self._nombre(o.product_id)) for o in version.outputs]
        return {"order_id": order.id, "status": order.status.value,
                "input_product_id": order.target_product_id,
                "input_product_name": self._nombre(order.target_product_id),
                "planned_weight": planeado, "warehouse_id": order.warehouse_id,
                "has_despiece": version is not None, "outputs": salidas}

    def _nombre(self, product_id: str) -> str:
        """El nombre que ve el operario. Sin catálogo de Productos (bases de
        prueba reducidas), el id: nunca revienta la captura."""
        try:
            fila = self._conn.execute("SELECT name FROM products WHERE id=?",
                                      (product_id,)).fetchone()
        except Exception:
            return product_id
        return str(fila[0]) if fila and fila[0] else product_id


class ExecuteProcessingOrderUseCase:
    def __init__(self, authorization, *, authorizer_authorization=None,
                 authorizer_checker=None) -> None:
        #: Política de quien opera (sesión) y la del AUTORIZADOR (otro usuario,
        #: `AuthorizerPermissionChecker` en producción).
        self._auth = authorization
        self._authorizer_auth = authorizer_authorization or authorization
        self._authorizer_checker = authorizer_checker

    # ── entrada ────────────────────────────────────────────────────────────
    def execute(self, connection, *, order_id: str, input_weight, outputs: list[dict],
                actor_user_id: str, operation_id: str,
                stock_authorizer_user_id: str | None = None, stock_reason: str | None = None,
                variance_authorizer_user_id: str | None = None,
                variance_reason: str | None = None, context=None) -> MeatProcessingResult:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.ORDER_START)
        except Exception as exc:  # noqa: BLE001 — permiso denegado
            return MeatProcessingResult.fail(str(exc), "PERMISSION_DENIED",
                                             operation_id=operation_id)
        preparado = self._prepare(connection, order_id=order_id, input_weight=input_weight,
                                  outputs=outputs, operation_id=operation_id)
        if isinstance(preparado, MeatProcessingResult):
            return preparado

        # ── autorizaciones (antes de mutar) ─────────────────────────────────
        if preparado["short"]:
            fallo = self._check_authorizer(
                stock_authorizer_user_id, stock_reason, actor_user_id,
                MeatProcessingPermissions.CONSUMPTION_OVERRIDE, operation_id,
                code="STOCK_AUTHORIZATION_REQUIRED",
                needed=(f"Existencia insuficiente de la entrada: disponible "
                        f"{preparado['available']} kg, se consumen {preparado['input_weight']} kg. "
                        "Otro usuario con permiso debe autorizar producir sin existencia."))
            if fallo:
                return fallo
        if preparado["out_of_tolerance"]:
            fuera = ", ".join(f"{r['product_id']} ({r['variance_pct']}%)"
                              for r in preparado["rows"] if r.get("_status") in _OUT)
            fallo = self._check_authorizer(
                variance_authorizer_user_id, variance_reason, actor_user_id,
                MeatProcessingPermissions.YIELD_OVERRIDE, operation_id,
                code="YIELD_AUTHORIZATION_REQUIRED",
                needed=(f"Rendimiento fuera de tolerancia en: {fuera}. Otro usuario con "
                        "permiso debe autorizar la diferencia (se abre caso en Mermas)."))
            if fallo:
                return fallo

        return self._run(connection, preparado, actor_user_id=actor_user_id,
                         operation_id=operation_id,
                         stock_authorizer=stock_authorizer_user_id, stock_reason=stock_reason,
                         variance_authorizer=variance_authorizer_user_id,
                         variance_reason=variance_reason, context=context)

    # ── validación completa, sin mutar nada ─────────────────────────────────
    def _prepare(self, connection, *, order_id, input_weight, outputs, operation_id):
        from backend.application.inventory.queries.availability_query_service import (
            InventoryAvailabilityQueryService,
        )
        from backend.application.pricing.queries.pricing_read_facade import PricingReadFacade
        from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
            MeatProcessingUnitOfWork,
        )
        from backend.infrastructure.db.repositories.products.cutting_scheme_repository import (
            CuttingSchemeRepository,
        )

        def fail(msg, code):
            return MeatProcessingResult.fail(msg, code, operation_id=operation_id)

        uow = MeatProcessingUnitOfWork(connection)
        order = uow.orders.get(order_id)
        if order is None:
            return fail("Orden no encontrada", "ORDER_NOT_FOUND")
        if order.status not in _RESUMABLE:
            return fail(f"La orden está {order.status.value}: sólo se ejecuta una orden liberada.",
                        "INVALID_STATE")
        version = (CuttingSchemeRepository(connection).get_version(order.cutting_scheme_version_id)
                   if order.cutting_scheme_version_id else None)
        if version is None:
            return fail("La orden no capturó un despiece (esquema de corte) al liberarse: "
                        "sólo se ejecutan órdenes con despiece.", "NO_DESPIECE")

        consumos = uow.consumptions.list_by_order(order.id)
        salidas_previas = uow.outputs.list_by_order(order.id)
        # Reanudación: lo ya registrado manda sobre lo capturado de nuevo.
        if consumos:
            entrada = sum((Decimal(str(c.actual_weight)) for c in consumos), Decimal("0"))
        else:
            try:
                entrada = Decimal(str(input_weight))
            except Exception:
                entrada = Decimal("0")
        if entrada <= 0:
            return fail("Captura el peso real de la entrada consumida.", "INVALID_INPUT")

        plan = {o.product_id: o for o in version.outputs}
        # El despiece habla el tipo de salida de Productos; Cárnico, el suyo. Se
        # traduce AQUÍ, antes de mutar: un tipo sin equivalente no debe
        # descubrirse con la entrada ya descontada.
        tipos = {}
        for pid, salida in plan.items():
            try:
                tipos[pid] = OutputType(salida.output_type.value)
            except ValueError:
                return fail(f"Tipo de salida sin equivalente en Cárnico: "
                            f"{salida.output_type.value}", "INVALID_OUTPUT")
        if salidas_previas:
            reales = {}
            for s in salidas_previas:
                reales[s.product_id] = reales.get(s.product_id, Decimal("0")) + s.weight
        else:
            reales = {}
            for linea in outputs or []:
                pid = str(linea.get("product_id") or "")
                if pid not in plan:
                    return fail(f"El producto {pid} no es salida del despiece de la orden.",
                                "INVALID_OUTPUT")
                peso = Decimal(str(linea.get("weight") or 0))
                if peso < 0:
                    return fail("Los pesos no pueden ser negativos.", "INVALID_OUTPUT")
                reales[pid] = reales.get(pid, Decimal("0")) + peso
        if not any(v > 0 for p, v in reales.items() if plan[p].output_type.value not in _NO_STOCK):
            return fail("Captura el peso de al menos una salida productiva.", "INVALID_OUTPUT")

        branch = order.branch_id
        precios = PricingReadFacade(connection)
        costo_entrada = precios.unit_cost(order.target_product_id, branch)
        if costo_entrada is None:
            return fail("La entrada no tiene costo (Costos): no se puede repartir un costo "
                        "inventado entre los cortes.", "MISSING_INPUT_COST")
        costo_total = (Decimal(str(costo_entrada)) * entrada).quantize(_PCT, rounding=ROUND_HALF_UP)

        def _precio(pid):
            try:
                return precios.sale_price(pid, branch_id=branch).price
            except Exception:
                return None

        try:
            reparto = RelativeSalesValueCostAllocation().allocate(costo_total, [
                AllocationInput(pid, plan[pid].output_type.value, peso,
                                None if plan[pid].output_type.value in _NO_STOCK else _precio(pid))
                for pid, peso in reales.items() if peso > 0])
        except CostAllocationError as exc:
            return fail(str(exc), "COST_ALLOCATION_FAILED")
        por_producto = {a.product_id: a for a in reparto}

        tol = YieldToleranceSettingsQueryService(connection).get()
        filas, peor = [], []
        for pid, salida in plan.items():
            esperado = (salida.quantity * entrada).quantize(_Q)
            real = reales.get(pid, Decimal("0")).quantize(_Q)
            variacion = (((real - esperado) / esperado) * 100).quantize(_PCT) if esperado > 0 else None
            estado = (YieldReconciliationPolicy.classify(
                variacion, warning_pct=tol.warning_pct, tolerance_pct=tol.tolerance_pct,
                critical_pct=tol.critical_pct)
                if salida.output_type.value not in _NO_STOCK else YieldStatus.WITHIN_TOLERANCE)
            if estado in _OUT:
                peor.append(pid)
            a = por_producto.get(pid)
            filas.append({
                "product_id": pid, "output_type": salida.output_type.value,
                "input_product_id": order.target_product_id, "input_weight": entrada,
                "input_unit_cost": Decimal(str(costo_entrada)), "expected_weight": esperado,
                "actual_weight": real, "difference_weight": real - esperado,
                "expected_yield_pct": (salida.quantity * 100).quantize(_PCT),
                "yield_pct": ((real / entrada) * 100).quantize(_PCT),
                "variance_pct": variacion,
                "unit_price": a.unit_price if a else None,
                "allocated_cost": a.allocated_cost if a else Decimal("0"),
                "unit_cost": a.unit_cost if a else Decimal("0"),
                "_status": estado})

        disponible = None
        corto = False
        if not any(c.status is ConsumptionStatus.POSTED for c in consumos):
            disponible = InventoryAvailabilityQueryService(connection).get_availability(
                product_id=order.target_product_id, branch_id=branch,
                warehouse_id=order.warehouse_id).available
            corto = disponible < entrada
        return {"order": order, "version": version, "plan": plan, "types": tipos,
                "input_weight": entrada,
                "reales": reales, "input_cost": Decimal(str(costo_entrada)),
                "allocation": por_producto, "rows": filas, "out_of_tolerance": bool(peor),
                "short": corto, "available": disponible, "tolerances": tol}

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

    # ── mutación, paso a paso y reanudable ──────────────────────────────────
    def _run(self, connection, p, *, actor_user_id, operation_id, stock_authorizer,
             stock_reason, variance_authorizer, variance_reason, context):
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
            RecordQualityDecisionUseCase,
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
        from backend.infrastructure.integrations.meat_processing_ports import (
            CanonicalProductionConsumptionAdapter,
            CanonicalProductionReceiptAdapter,
            LossesYieldVarianceAdapter,
            ProjectedCostAllocationAdapter,
        )

        order = p["order"]
        oid = order.id
        auth = self._auth
        common = {"actor_user_id": actor_user_id, "context": context}

        def paso(nombre, result):
            if not result.success and not result.data.get("already_processed"):
                raise _StepFailed(nombre, result)
            return result

        try:
            if order.status is ProcessingOrderStatus.RELEASED:
                paso("iniciar", StartProcessExecutionUseCase(auth).execute(
                    connection, order_id=oid, operation_id=new_uuid(), **common))

            uow = MeatProcessingUnitOfWork(connection)
            consumos = uow.consumptions.list_by_order(oid)
            if not consumos:
                paso("capturar consumo", CaptureMaterialConsumptionUseCase(auth).execute(
                    connection, order_id=oid, operation_id=new_uuid(),
                    product_id=order.target_product_id, warehouse_id=order.warehouse_id,
                    planned_quantity=Decimal("0"),
                    planned_weight=Decimal(str(order.planned_weight or p["input_weight"])),
                    actual_quantity=Decimal("0"), actual_weight=p["input_weight"],
                    unit="kg", **common))
                consumos = uow.consumptions.list_by_order(oid)
            consumo_port = CanonicalProductionConsumptionAdapter(
                connection, branch_id=order.branch_id, actor_user_id=actor_user_id,
                document_id=oid, unit_costs={order.target_product_id: p["input_cost"]},
                negative_authorized=bool(p["short"] and stock_authorizer))
            for c in consumos:
                if c.status is ConsumptionStatus.POSTED:
                    continue
                r = PostMaterialConsumptionUseCase(auth, inventory_port=consumo_port).execute(
                    connection, consumption_id=c.id, operation_id=new_uuid(),
                    actor_user_id=actor_user_id, context=context)
                if not r.success:
                    raise _StepFailed("descontar la entrada", r, consumo_port.last_error)
            lotes_entrada = tuple(c.lot_id for c in uow.consumptions.list_by_order(oid) if c.lot_id)

            if not uow.outputs.list_by_order(oid):
                esperado_principal = sum(
                    (r["expected_weight"] for r in p["rows"] if r["output_type"] == "MAIN_PRODUCT"),
                    Decimal("0"))
                tol = p["tolerances"]
                paso("registrar salidas", RecordProcessOutputsUseCase(auth).execute(
                    connection, order_id=oid, operation_id=new_uuid(),
                    input_quantity=Decimal("0"), input_weight=p["input_weight"],
                    expected_output_quantity=Decimal("0"),
                    expected_output_weight=esperado_principal,
                    outputs=[{"product_id": pid, "output_type": p["types"][pid],
                              "weight": peso, "unit": "kg"}
                             for pid, peso in p["reales"].items() if peso > 0],
                    warning_pct=tol.warning_pct, tolerance_pct=tol.tolerance_pct,
                    critical_pct=tol.critical_pct, **common))

            for s in uow.outputs.list_by_order(oid):
                if s.quality_status is OutputQualityStatus.PENDING_INSPECTION:
                    paso("calidad", RecordQualityDecisionUseCase(auth).execute(
                        connection, output_id=s.id, operation_id=new_uuid(),
                        decision=OutputQualityStatus.RELEASED, **common))

            lote = f"OP-{oid[-8:].upper()}-{datetime.now(timezone.utc):%Y%m%d}"
            recepcion = CanonicalProductionReceiptAdapter(
                connection, branch_id=order.branch_id, actor_user_id=actor_user_id,
                document_id=oid, lot_code=lote, input_lot_ids=lotes_entrada,
                unit_costs={pid: a.unit_cost for pid, a in p["allocation"].items()})
            for s in uow.outputs.list_by_order(oid):
                if (s.output_type.value in _NO_STOCK or s.inventory_operation_id
                        or s.quality_status is not OutputQualityStatus.RELEASED):
                    continue
                r = PostProcessOutputUseCase(auth, inventory_port=recepcion).execute(
                    connection, output_id=s.id, operation_id=new_uuid(),
                    actor_user_id=actor_user_id, context=context)
                if not r.success:
                    raise _StepFailed("recibir salidas", r, recepcion.last_error)

            filas = [{k: v for k, v in r.items() if not k.startswith("_")} | {
                "input_lot_id": lotes_entrada[0] if lotes_entrada else None,
                "output_lot_id": recepcion.lot_ids.get(r["product_id"])} for r in p["rows"]]
            ProcessingOutputResultsRepository(connection).replace_for_order(oid, filas)
            with MeatProcessingUnitOfWork(connection) as audit_uow:
                audit_uow.audit.record(
                    entity_type="ProcessingOrder", entity_id=oid, action="EXECUTED",
                    user_id=actor_user_id, operation_id=operation_id,
                    after_json=json.dumps({
                        "input_weight": str(p["input_weight"]),
                        "stock_authorized_by": stock_authorizer if p["short"] else None,
                        "stock_reason": stock_reason if p["short"] else None,
                        "variance_authorized_by": (variance_authorizer
                                                   if p["out_of_tolerance"] else None),
                        "variance_reason": variance_reason if p["out_of_tolerance"] else None,
                    }), branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                    processing_order_id=oid)

            if uow.orders.get(oid).status is not ProcessingOrderStatus.COMPLETED:
                paso("completar", CompleteProcessExecutionUseCase(auth).execute(
                    connection, order_id=oid, operation_id=new_uuid(), **common))

            conciliaciones = uow.yield_reconciliations.list_by_order(oid)
            for conc in conciliaciones:
                if conc.status is YieldStatus.APPROVED:
                    continue
                if conc.status in _OUT:
                    paso("caso de merma", RequestLossCaseForYieldVarianceUseCase(
                        auth, loss_case_port=LossesYieldVarianceAdapter(
                            connection, branch_id=order.branch_id,
                            warehouse_id=order.warehouse_id, actor_user_id=actor_user_id,
                            unit_cost=p["input_cost"], notes=variance_reason or "")).execute(
                        connection, reconciliation_id=conc.id, operation_id=new_uuid(),
                        actor_user_id=actor_user_id, context=context))
                aprobador, politica = ((variance_authorizer, self._authorizer_auth)
                                       if p["out_of_tolerance"] and variance_authorizer
                                       else (actor_user_id, auth))
                paso("aprobar rendimiento", ApproveYieldReconciliationUseCase(politica).execute(
                    connection, reconciliation_id=conc.id, operation_id=new_uuid(),
                    actor_user_id=aprobador))

            costo = ProjectedCostAllocationAdapter(connection, actor_user_id=actor_user_id, lines=[
                {"product_id": pid, "quantity": a.weight, "unit_cost": a.unit_cost}
                for pid, a in p["allocation"].items() if a.allocated_cost > 0])
            cierre = CloseProcessingOrderUseCase(auth, cost_allocation_port=costo).execute(
                connection, order_id=oid, operation_id=new_uuid(), **common)
            if not cierre.success:
                raise _StepFailed("cerrar", cierre, costo.last_error)
        except _StepFailed as exc:
            logger.warning("orden %s: falló '%s': %s", oid, exc.step, exc.result.message)
            detalle = f" ({exc.detail})" if exc.detail else ""
            return MeatProcessingResult.fail(
                f"No se pudo {exc.step}: {exc.result.message}{detalle}. Lo ya hecho quedó "
                "registrado; vuelve a ejecutar para continuar.",
                exc.result.error_code or "EXECUTION_STEP_FAILED", operation_id=operation_id,
                step=exc.step, pending_items=exc.result.data.get("pending_items"))

        resultados = ProcessingOutputResultsRepository(connection).list_by_order(oid)
        return MeatProcessingResult.ok(
            "Orden ejecutada y cerrada", entity_id=oid, operation_id=operation_id,
            results=resultados, out_of_tolerance=p["out_of_tolerance"],
            stock_authorized=bool(p["short"]))


class _StepFailed(Exception):
    def __init__(self, step, result, detail=None) -> None:
        super().__init__(step)
        self.step, self.result, self.detail = step, result, detail
