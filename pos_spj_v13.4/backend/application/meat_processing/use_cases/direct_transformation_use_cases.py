"""Transformación directa: despiezar un lote YA recibido en una sola acción
(auditoría de Producción cárnica 32cfbf, decisión del usuario, 2026-10-16).

La operación cotidiana —llegó el pollo, se despieza— exigía el flujo industrial
completo (crear, que OTRO apruebe, preparar, liberar, ejecutar). Aquí quien
opera ve una acción; por dentro se reutiliza el MISMO motor de órdenes:

1. crear la orden de despiece con origen `DIRECT_TRANSFORMATION` y el lote
   elegido como referencia (el folio es el de cualquier orden);
2. aprobarla por su propio permiso (`approve_direct_transformation`; una orden
   normal sigue exigiendo aprobador distinto);
3. preparar: congelar la definición (el perfil de rendimiento manda) y reservar
   EXACTAMENTE ese lote (`MANUAL_AUTHORIZED`), sólo si Calidad lo liberó;
4. liberar;
5. ejecutar con los pesos reales capturados: consume lo reservado, da entrada a
   los cortes con lotes hijos y genealogía, pide calidad y costeo, concilia la
   merma y cierra.

Ninguna escritura a Inventario sale de aquí: las hacen los casos de uso de
siempre. Las etapas corren con `DirectTransformationStageAuthorization` (basta
el permiso propio); la desviación de rendimiento la autoriza OTRO usuario con
`YIELD_OVERRIDE`, igual que en una orden normal.

Idempotente y reanudable: la bitácora `direct_transformations` guarda la orden
y el UUIDv7 de cada etapa. Si algo falla (lote insuficiente, costeo
incompleto, autorización pendiente), la orden queda visible en Órdenes y
repetir con el mismo `operation_id` continúa desde donde quedó.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.result import MeatProcessingResult
from backend.application.meat_processing.use_cases._shared import fail as _fail
from backend.application.meat_processing.use_cases._shared import scope_fail as _scope_fail
from backend.domain.meat_processing.entities.processing_order import (
    DIRECT_TRANSFORMATION_SOURCE,
)
from backend.domain.meat_processing.enums import ProcessingOrderStatus, ProcessType
from backend.domain.meat_processing.exceptions import MeatProcessingPermissionDeniedError

_S = ProcessingOrderStatus
_EXECUTABLE = {_S.RELEASED, _S.IN_PROGRESS, _S.PENDING_QUALITY, _S.PENDING_RECONCILIATION,
               _S.PARTIALLY_COMPLETED, _S.COMPLETED}


class ExecuteDirectTransformationUseCase:
    def __init__(self, authorization, *, create_uc, approve_uc, prepare_uc, release_uc,
                 execute_uc, lots_query_factory) -> None:
        #: Autorización REAL de la sesión: aquí sólo se pide el permiso propio.
        self._auth = authorization
        #: Casos de uso de la orden construidos con la autorización de ETAPAS.
        self._create, self._approve = create_uc, approve_uc
        self._prepare, self._release, self._execute = prepare_uc, release_uc, execute_uc
        #: conexión → `DirectTransformationQueryService` (lote elegible).
        self._lots = lots_query_factory

    def execute(self, connection, *, operation_id: str, branch_id: str, lot_id: str,
                input_weight, outputs: list[dict], actor_user_id: str,
                estimated_product_ids=(), estimate_reason: str | None = None,
                variance_authorizer_user_id: str | None = None,
                variance_reason: str | None = None, context=None) -> MeatProcessingResult:
        from backend.infrastructure.db.repositories.meat_processing.direct_transformation_repository import (
            DirectTransformationRepository,
        )
        from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
            MeatProcessingUnitOfWork,
        )

        try:
            self._auth.require(actor_user_id,
                               MeatProcessingPermissions.DIRECT_TRANSFORMATION_EXECUTE)
        except MeatProcessingPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        repo = DirectTransformationRepository(connection)
        registro = repo.get_by_operation(operation_id)
        if registro is not None and registro.status == "COMPLETED":
            return MeatProcessingResult.ok(
                "Transformación ya registrada (idempotente)",
                entity_id=registro.processing_order_id, operation_id=operation_id,
                already_processed=True, order_id=registro.processing_order_id,
                folio=self._folio(connection, registro.processing_order_id))

        if registro is None:
            entrada = Decimal(str(input_weight or 0))
            if entrada <= 0:
                return MeatProcessingResult.fail(
                    "Captura los kilos de entrada a transformar.", "INVALID_QUANTITY",
                    operation_id=operation_id)
            lote = self._lots(connection).lot(branch_id, lot_id)
            if lote is None:
                return MeatProcessingResult.fail(
                    "Ese lote ya no está disponible en el almacén de producción.",
                    "LOT_NOT_AVAILABLE", operation_id=operation_id)
            if not lote.eligible:
                return MeatProcessingResult.fail(lote.blocked_reason, "LOT_NOT_RELEASED",
                                                 operation_id=operation_id)
            if entrada > lote.available_kg:
                return MeatProcessingResult.fail(
                    f"El lote tiene {lote.available_kg} kg disponibles; se piden {entrada}.",
                    "INSUFFICIENT_AVAILABILITY", operation_id=operation_id,
                    available=str(lote.available_kg))
            denegado = _scope_fail(context, branch_id, lote.warehouse_id, operation_id)
            if denegado is not None:
                return denegado
            registro = repo.start(
                operation_id=operation_id, branch_id=branch_id,
                warehouse_id=lote.warehouse_id, input_product_id=lote.product_id,
                lot_id=lot_id, input_weight=entrada, actor_user_id=actor_user_id)
            connection.commit()
        else:
            denegado = _scope_fail(context, registro.branch_id, registro.warehouse_id,
                                   operation_id)
            if denegado is not None:
                return denegado

        pasos = registro.step_operations
        orden_id = registro.processing_order_id

        def fallar(resultado: MeatProcessingResult) -> MeatProcessingResult:
            repo.update(registro.id, status="FAILED", last_error=resultado.message)
            connection.commit()
            datos = dict(resultado.data)
            datos.update(order_id=orden_id, folio=self._folio(connection, orden_id))
            return MeatProcessingResult.fail(resultado.message,
                                             resultado.error_code or "DIRECT_TRANSFORMATION_FAILED",
                                             operation_id=operation_id, **datos)

        if orden_id is None:
            r = self._create.execute(
                connection, operation_id=pasos["create"], branch_id=registro.branch_id,
                warehouse_id=registro.warehouse_id, process_type=ProcessType.DISASSEMBLY,
                target_product_id=registro.input_product_id, planned_quantity=Decimal("0"),
                planned_weight=Decimal(registro.input_weight), actor_user_id=actor_user_id,
                source_type=DIRECT_TRANSFORMATION_SOURCE, source_reference_id=registro.lot_id,
                context=context)
            if not r.success:
                return fallar(r)
            orden_id = r.entity_id
            repo.update(registro.id, processing_order_id=orden_id)
            connection.commit()

        ejecucion: MeatProcessingResult | None = None
        for _ in range(6):   # a lo sumo una vuelta por etapa
            orden = MeatProcessingUnitOfWork(connection).orders.get(orden_id)
            estado = orden.status
            if estado is _S.CLOSED:
                break
            if estado is _S.PENDING_APPROVAL:
                r = self._approve.execute(connection, order_id=orden_id,
                                          operation_id=pasos["approve"],
                                          actor_user_id=actor_user_id, context=context,
                                          direct_transformation=True)
            elif estado in (_S.APPROVED, _S.MATERIALS_PENDING):
                r = self._prepare.execute(connection, order_id=orden_id,
                                          operation_id=pasos["prepare"],
                                          actor_user_id=actor_user_id, context=context)
                if r.success and not r.data.get("ready", False):
                    faltante = (r.data.get("shortages") or [{}])[0]
                    r = MeatProcessingResult.fail(
                        faltante.get("message") or "El lote no alcanza para la transformación.",
                        "INSUFFICIENT_AVAILABILITY", operation_id=operation_id,
                        shortages=r.data.get("shortages"))
            elif estado is _S.READY:
                r = self._release.execute(connection, order_id=orden_id,
                                          operation_id=pasos["release"],
                                          actor_user_id=actor_user_id, context=context)
            elif estado in _EXECUTABLE:
                r = self._execute.execute(
                    connection, order_id=orden_id, operation_id=pasos["execute"],
                    actor_user_id=actor_user_id,
                    inputs=[{"product_id": registro.input_product_id,
                             "weight": Decimal(registro.input_weight)}],
                    outputs=outputs, estimated_product_ids=estimated_product_ids,
                    estimate_reason=estimate_reason,
                    variance_authorizer_user_id=variance_authorizer_user_id,
                    variance_reason=variance_reason, context=context)
                ejecucion = r
            else:
                r = MeatProcessingResult.fail(
                    f"La orden de esta transformación está {estado.value} y ya no puede "
                    "continuar.", "INVALID_STATE", operation_id=operation_id)
            if not r.success:
                return fallar(r)

        repo.update(registro.id, status="COMPLETED")
        connection.commit()
        datos = dict(ejecucion.data) if ejecucion is not None else {}
        datos.update(order_id=orden_id, folio=self._folio(connection, orden_id))
        return MeatProcessingResult.ok(
            f"Transformación registrada: orden {datos['folio'] or ''}".strip(),
            entity_id=orden_id, operation_id=operation_id, **datos)

    @staticmethod
    def _folio(connection, order_id: str | None) -> str | None:
        if not order_id:
            return None
        from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
            MeatProcessingUnitOfWork,
        )
        orden = MeatProcessingUnitOfWork(connection).orders.get(order_id)
        return orden.folio if orden is not None else None
