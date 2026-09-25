"""Caso de merma por variación de rendimiento — frontera de aplicación de MERMAS.

Antes, el adaptador de Procesamiento construía el `LossCase` y lo guardaba
llamando directo a `ProductionLossRepository`: Procesamiento decidía la
clasificación, la valuación y escribía tablas de Mermas. Ahora Procesamiento
sólo PIDE el caso (`LossCaseRequestPort`) y es Mermas quien:

- exige su permiso (concesión explícita a `meat_processing`, atada al operador);
- clasifica (`YIELD_VARIANCE`, origen PRODUCCIÓN) con su causa configurada;
- valúa con el costo vigente del producto (Costos/Precios), no con uno que le
  pasen;
- registra el caso SIN movimiento de inventario: el consumo y las salidas ya
  movieron la existencia real, y un movimiento aquí la descontaría dos veces.

Idempotente por `operation_id`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.losses.authorization import LossAuthorizationPolicy
from backend.application.losses.permissions import LossPermissions
from backend.application.security.system_integration_authorization import (
    DelegatedIntegrationPermissionChecker,
    IntegrationGrant,
)
from backend.domain.losses.entities import LossCase, LossLine
from backend.domain.losses.enums import LossClassificationCode, LossOrigin
from backend.domain.losses.events import LossEvents, build_loss_event
from backend.domain.losses.exceptions import LossPermissionDeniedError
from backend.shared.ids import new_uuid

MEAT_PROCESSING_LOSSES_GRANT = IntegrationGrant(
    owner_context="losses", source_module="meat_processing",
    permissions=frozenset({LossPermissions.REPORT, LossPermissions.SUBMIT}))
_GRANTS = {MEAT_PROCESSING_LOSSES_GRANT.source_module: MEAT_PROCESSING_LOSSES_GRANT}


def losses_policy_for(source_module: str, actor_user_id: str) -> LossAuthorizationPolicy:
    grant = _GRANTS.get(source_module)
    if grant is None:
        raise LossPermissionDeniedError(f"Mermas no concede nada al módulo «{source_module}»")
    return LossAuthorizationPolicy(
        DelegatedIntegrationPermissionChecker(grant=grant, actor_user_id=actor_user_id))


@dataclass(frozen=True)
class YieldVarianceCaseResult:
    case_id: str | None
    message: str = ""
    already_processed: bool = False


class RequestYieldVarianceLossCaseUseCase:
    def __init__(self, authorization: LossAuthorizationPolicy, *, repository_factory=None,
                 cost_reader_factory=None) -> None:
        if authorization is None:
            raise ValueError("RequestYieldVarianceLossCaseUseCase requiere autorización")
        self._auth = authorization
        if repository_factory is None:
            from backend.infrastructure.persistence.production_loss_repository import (
                ProductionLossRepository,
            )
            repository_factory = ProductionLossRepository
        self._repo_factory = repository_factory
        self._cost_reader_factory = cost_reader_factory

    def _unit_cost(self, connection, product_id: str, branch_id: str) -> Decimal:
        if self._cost_reader_factory is not None:
            lector = self._cost_reader_factory(connection)
        else:
            from backend.application.pricing.queries.pricing_read_facade import (
                PricingReadFacade,
            )
            lector = PricingReadFacade(connection)
        costo = lector.unit_cost(product_id, branch_id)
        return Decimal(str(costo)) if costo is not None else Decimal("0")

    def execute(self, connection, *, operation_id: str, actor_user_id: str, branch_id: str,
                warehouse_id: str, source_document_id: str, product_id: str,
                expected_weight, actual_weight, difference_weight, lot_id: str | None = None,
                notes: str = "") -> YieldVarianceCaseResult:
        try:
            self._auth.require(actor_user_id, LossPermissions.REPORT)
            self._auth.require(actor_user_id, LossPermissions.SUBMIT)
        except LossPermissionDeniedError as exc:
            return YieldVarianceCaseResult(None, str(exc))
        repo = self._repo_factory(connection)
        previo = repo.find_case_by_operation(operation_id)
        if previo is not None:
            return YieldVarianceCaseResult(previo, "Caso ya registrado (idempotente)", True)
        causa = repo.yield_variance_reason()
        if not causa:
            return YieldVarianceCaseResult(
                None, "Mermas no tiene configurada la causa «Variación de rendimiento»")
        peso = abs(Decimal(str(difference_weight or 0)))
        if peso <= 0:
            return YieldVarianceCaseResult(None, "Sin diferencia de peso no hay merma que abrir")
        caso = LossCase(
            id=new_uuid(), operation_id=operation_id, branch_id=branch_id,
            warehouse_id=warehouse_id, reported_by_user_id=actor_user_id,
            classification=LossClassificationCode.YIELD_VARIANCE, origin=LossOrigin.PRODUCTION,
            reason_id=causa[1], source_document_id=source_document_id,
            notes=((notes or "Variación de rendimiento en producción")
                   + f" — esperado {expected_weight} kg, real {actual_weight} kg"))
        caso.add_line(LossLine(id=new_uuid(), product_id=product_id, lot_id=lot_id, weight=peso,
                               unit="kg",
                               unit_cost=self._unit_cost(connection, product_id, branch_id)))
        caso.submit(actor_user_id=actor_user_id)
        evento = build_loss_event(
            LossEvents.YIELD_VARIANCE_DETECTED, operation_id=caso.operation_id,
            entity_id=caso.id, branch_id=branch_id, warehouse_id=warehouse_id,
            user_id=actor_user_id, production_id=source_document_id, loss_weight=str(peso))
        repo.record_production_variance_case(caso, event=evento)
        return YieldVarianceCaseResult(caso.id, "Caso de merma registrado")
