"""Costeo real de una transformación productiva (contexto COSTOS).

Procesamiento publica hechos — qué consumió, qué produjo — y pide el costeo.
Costos decide:

- el costo de lo consumido (costo vigente de Precios/Costos de cada insumo);
- el método de reparto (configurable: `costing.processing.allocation_method`);
- cuánto vale cada salida y cuánto se reconoce como merma.

Resultado: una asignación persistida por orden (idempotente: reintentar
devuelve la misma) y dos hechos en `costing_outbox`:

- `PRODUCTION_OUTPUT_COSTED` → Precios (`ProductCostProjectionHandler`, ya
  suscrito en `wire_pricing`) actualiza el costo promedio de cada salida;
- `PROCESSING_COST_ALLOCATED` → Finanzas (`ProductionCompletedHandler`)
  contabiliza la producción y la merma.

Procesamiento sólo recibe la referencia (`allocation_id`). Ningún `event_id`
ni `operation_id` se deriva concatenando: todos son UUIDv7 y se guardan.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from backend.application.security.system_integration_authorization import (
    DelegatedIntegrationPermissionChecker,
    IntegrationGrant,
)
from backend.domain.costing.services.joint_cost_allocation import (
    AllocationInput,
    AllocationMethod,
    CostAllocationError,
    JointCostAllocator,
)
from backend.infrastructure.db.repositories.costing.processing_cost_repository import (
    CostingOutboxRepository,
    ProcessingCostRepository,
    StoredAllocationLine,
)
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.costing.processing")

COST_PROCESSING = "COSTOS.produccion.costear"
PRODUCTION_OUTPUT_COSTED = "PRODUCTION_OUTPUT_COSTED"
PROCESSING_COST_ALLOCATED = "PROCESSING_COST_ALLOCATED"

METHOD_KEY = "costing.processing.allocation_method"
FACTORS_KEY = "costing.processing.allocation_factors"
SEPARABLE_KEY = "costing.processing.separable_costs"
#: Decisión vigente del usuario (2026-09-19): valor de venta relativo. Es el
#: valor por omisión, no una regla fija: se cambia en configuración.
DEFAULT_METHOD = AllocationMethod.RELATIVE_SALES_VALUE

_CENT = Decimal("0.01")

#: Costos concede a Procesamiento pedir el costeo de sus órdenes. Nada más.
MEAT_PROCESSING_COSTING_GRANT = IntegrationGrant(
    owner_context="costing", source_module="meat_processing",
    permissions=frozenset({COST_PROCESSING}))
_GRANTS = {MEAT_PROCESSING_COSTING_GRANT.source_module: MEAT_PROCESSING_COSTING_GRANT}


class CostingPermissionDeniedError(PermissionError):
    pass


class CostingAuthorizationPolicy:
    def __init__(self, checker) -> None:
        if checker is None:
            raise ValueError("CostingAuthorizationPolicy requiere un verificador de permisos")
        self._checker = checker

    def require(self, user_id: str, permission_code: str) -> None:
        if not user_id or not self._checker.has_permission(user_id, permission_code):
            raise CostingPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")


def costing_policy_for(source_module: str, actor_user_id: str) -> CostingAuthorizationPolicy:
    grant = _GRANTS.get(source_module)
    if grant is None:
        raise CostingPermissionDeniedError(f"Costos no concede nada al módulo «{source_module}»")
    return CostingAuthorizationPolicy(
        DelegatedIntegrationPermissionChecker(grant=grant, actor_user_id=actor_user_id))


# ── hechos que publica quien produce ────────────────────────────────────────
@dataclass(frozen=True)
class ConsumedMaterial:
    product_id: str
    quantity: Decimal
    lot_id: str | None = None


@dataclass(frozen=True)
class ProducedOutput:
    product_id: str
    output_type: str
    quantity: Decimal
    lot_id: str | None = None


@dataclass(frozen=True)
class ProductionCostFacts:
    source_module: str
    processing_order_id: str
    branch_id: str
    process_type: str
    consumed: tuple[ConsumedMaterial, ...]
    produced: tuple[ProducedOutput, ...]


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class ProcessingCostSettingsQueryService:
    """Método de reparto y sus parámetros, desde `configuraciones`."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def _get(self, key: str) -> str | None:
        try:
            fila = self._conn.execute("SELECT valor FROM configuraciones WHERE clave=?",
                                      (key,)).fetchone()
        except Exception:  # noqa: BLE001 — sin tabla de configuración: valores por omisión
            return None
        return None if fila is None else fila[0]

    def method(self) -> AllocationMethod:
        valor = self._get(METHOD_KEY)
        try:
            return AllocationMethod(valor) if valor else DEFAULT_METHOD
        except ValueError:
            raise CostAllocationError(f"Método de reparto desconocido en configuración: {valor}")

    def _map(self, key: str) -> dict[str, Decimal]:
        crudo = self._get(key)
        if not crudo:
            return {}
        datos = json.loads(crudo)
        return {pid: d for pid, v in datos.items() if (d := _dec(v)) is not None}

    def factors(self) -> dict[str, Decimal]:
        return self._map(FACTORS_KEY)

    def separable_costs(self) -> dict[str, Decimal]:
        return self._map(SEPARABLE_KEY)


@dataclass(frozen=True)
class CostingResult:
    success: bool
    allocation_id: str | None = None
    message: str = ""
    error_code: str | None = None
    already_processed: bool = False


class AllocateProductionCostUseCase:
    def __init__(self, authorization: CostingAuthorizationPolicy, *, currency_code: str = "MXN",
                 pricing_factory=None, settings_factory=None) -> None:
        if authorization is None:
            raise ValueError("AllocateProductionCostUseCase requiere autorización explícita")
        self._auth = authorization
        self._currency = currency_code
        self._pricing_factory = pricing_factory
        self._settings_factory = settings_factory or ProcessingCostSettingsQueryService

    def _pricing(self, connection):
        if self._pricing_factory is not None:
            return self._pricing_factory(connection)
        from backend.application.pricing.queries.pricing_read_facade import PricingReadFacade
        return PricingReadFacade(connection)

    def preview(self, connection, facts: ProductionCostFacts, *,
                actor_user_id: str) -> CostingResult:
        """¿Se puede costear esto? Misma valuación y mismo reparto que
        `execute`, SIN escribir nada. Quien produce lo pregunta antes de mover
        existencia, para no descubrir a mitad de camino que falta un costo o un
        precio."""
        try:
            self._auth.require(actor_user_id, COST_PROCESSING)
        except CostingPermissionDeniedError as exc:
            return CostingResult(False, message=str(exc), error_code="PERMISSION_DENIED")
        previa = ProcessingCostRepository(connection).get_by_order(facts.processing_order_id)
        if previa is not None:
            return CostingResult(True, previa.id, "Orden ya costeada", already_processed=True)
        calculo = self._compute(connection, facts)
        if isinstance(calculo, CostingResult):
            return calculo
        return CostingResult(True, None, "Se puede costear")

    def _compute(self, connection, facts: ProductionCostFacts):
        """Valúa lo consumido y reparte entre lo producido. Devuelve un
        `CostingResult` fallido o el cálculo; no escribe."""
        if not facts.consumed or not facts.produced:
            return CostingResult(False, message="Sin consumo ni producción no hay qué costear",
                                 error_code="NO_FACTS")
        precios = self._pricing(connection)
        ajustes = self._settings_factory(connection)
        try:
            metodo = ajustes.method()
        except CostAllocationError as exc:
            return CostingResult(False, message=str(exc), error_code="COSTING_CONFIGURATION")

        # ── costo de lo consumido ───────────────────────────────────────
        entradas: list[StoredAllocationLine] = []
        costo_entrada = Decimal("0")
        sin_costo = []
        for c in facts.consumed:
            unitario = precios.unit_cost(c.product_id, facts.branch_id)
            if unitario is None:
                sin_costo.append(c.product_id)
                continue
            importe = (Decimal(str(unitario)) * c.quantity).quantize(_CENT, ROUND_HALF_UP)
            costo_entrada += importe
            entradas.append(StoredAllocationLine(
                "INPUT", c.product_id, None, c.lot_id, c.quantity, None, Decimal("0"),
                importe, Decimal(str(unitario))))
        if sin_costo:
            return CostingResult(
                False, message="Insumos sin costo vigente; no se reparte un costo inventado: "
                + ", ".join(sin_costo), error_code="MISSING_INPUT_COST")

        # ── reparto entre lo producido ──────────────────────────────────
        factores, separables = ajustes.factors(), ajustes.separable_costs()

        def _precio(pid):
            try:
                return precios.sale_price(pid, branch_id=facts.branch_id).price
            except Exception:  # noqa: BLE001 — sin precio: el método decidirá si es error
                return None

        salidas_in = [AllocationInput(
            product_id=o.product_id, output_type=o.output_type, weight=o.quantity,
            unit_price=_precio(o.product_id) if o.output_type not in ("WASTE", "LOSS") else None,
            standard_unit_cost=precios.unit_cost(o.product_id, facts.branch_id),
            separable_unit_cost=separables.get(o.product_id, Decimal("0")),
            factor=factores.get(o.product_id)) for o in facts.produced if o.quantity > 0]
        try:
            repartidas = JointCostAllocator(metodo).allocate(costo_entrada, salidas_in)
        except CostAllocationError as exc:
            return CostingResult(False, message=str(exc), error_code="COST_ALLOCATION_FAILED")
        return metodo, entradas, costo_entrada, repartidas

    def execute(self, connection, facts: ProductionCostFacts, *, operation_id: str,
                actor_user_id: str) -> CostingResult:
        try:
            self._auth.require(actor_user_id, COST_PROCESSING)
        except CostingPermissionDeniedError as exc:
            return CostingResult(False, message=str(exc), error_code="PERMISSION_DENIED")
        repo = ProcessingCostRepository(connection)
        previa = repo.get_by_order(facts.processing_order_id)
        if previa is not None:
            return CostingResult(True, previa.id, "Orden ya costeada (idempotente)",
                                 already_processed=True)
        calculo = self._compute(connection, facts)
        if isinstance(calculo, CostingResult):
            return calculo
        metodo, entradas, costo_entrada, repartidas = calculo
        lotes = {o.product_id: o.lot_id for o in facts.produced}
        salidas = [StoredAllocationLine(
            "OUTPUT", a.product_id, a.output_type, lotes.get(a.product_id), a.weight,
            a.unit_price, a.basis_value, a.allocated_cost, a.unit_cost) for a in repartidas]
        merma = sum((a.allocated_cost for a in repartidas
                     if a.output_type in ("WASTE", "LOSS")), Decimal("0"))
        valor_salidas = costo_entrada - merma

        allocation_id = new_uuid()
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        repo.add(allocation_id=allocation_id, operation_id=operation_id,
                 processing_order_id=facts.processing_order_id,
                 source_module=facts.source_module, branch_id=facts.branch_id,
                 process_type=facts.process_type, method=metodo.value,
                 currency_code=self._currency, input_cost_total=costo_entrada,
                 output_value_total=valor_salidas, waste_value_total=merma,
                 created_by_user_id=actor_user_id, lines=entradas + salidas)
        outbox = CostingOutboxRepository(connection)
        costo_evento = new_uuid()
        outbox.enqueue(event_id=costo_evento, event_name=PRODUCTION_OUTPUT_COSTED,
                       operation_id=operation_id, payload={
                           "event_id": costo_evento, "operation_id": operation_id,
                           "user_id": actor_user_id, "occurred_at": ahora,
                           "source_module": "costing",
                           "source_document_id": facts.processing_order_id,
                           "cost_allocation_id": allocation_id,
                           "lines": [{"product_id": a.product_id, "quantity": str(a.weight),
                                      "unit_cost": str(a.unit_cost)}
                                     for a in repartidas if a.allocated_cost > 0
                                     and a.output_type not in ("WASTE", "LOSS")]})
        finanzas_evento = new_uuid()
        outbox.enqueue(event_id=finanzas_evento, event_name=PROCESSING_COST_ALLOCATED,
                       operation_id=operation_id, payload={
                           "event_id": finanzas_evento, "operation_id": operation_id,
                           "occurred_at": ahora, "currency_code": self._currency,
                           "production_id": facts.processing_order_id,
                           "cost_allocation_id": allocation_id,
                           "branch_id": facts.branch_id, "method": metodo.value,
                           "input_cost": str(costo_entrada),
                           "output_value": str(valor_salidas), "waste_value": str(merma)})
        connection.commit()
        logger.info("orden %s costeada por %s: entrada %s, salidas %s, merma %s",
                    facts.processing_order_id, metodo.value, costo_entrada, valor_salidas, merma)
        return CostingResult(True, allocation_id, "Costo de producción asignado")
