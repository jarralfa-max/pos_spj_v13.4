# sync/domain_validators/meat_processing_validator.py — PROC-21
"""Domain validator for the new Procesamiento Cárnico schema (§21 offline).

`ProductionValidator` (production_validator.py) still validates the legacy
`production_batches`/`production_outputs`/`production_cost_ledger` tables,
untouched by this refactor and still read by `modulos/produccion.py` until
PROC-25 — see `docs/refactor/PROC-0_legacy_audit.md`. This is its sibling for
the born-clean bounded context built in PROC-2/PROC-3 onward
(`processing_orders`, `yield_reconciliations`, `process_outputs`): UUIDv7 ids,
Decimal-safe (no ``float``), English field names matching
`backend/infrastructure/db/schema/meat_processing_schema.py`. Added rather
than folded into `ProductionValidator` so the legacy validator's own tests
(``tests/test_refactor_v133.py::TestProductionValidator``) keep passing
unchanged against the tables they were written for.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from sync.domain_validators.base import DomainValidator

logger = logging.getLogger("spj.sync.validators.meat_processing")

MEAT_PROCESSING_TABLES = frozenset({
    "processing_orders", "yield_reconciliations", "process_outputs",
})

#: ProcessingOrderStatus values reachable before CLOSED (backend.domain.
#: meat_processing.enums.ProcessingOrderStatus) — a closed order syncing back
#: to any of these from a stale remote write is a reopen attempt.
_OPEN_ORDER_STATUSES = frozenset({
    "DRAFT", "PENDING_APPROVAL", "APPROVED", "MATERIALS_PENDING", "READY",
    "RELEASED", "IN_PROGRESS", "PAUSED",
})


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal("0")


class MeatProcessingValidator(DomainValidator):
    """Valida reglas de negocio del núcleo productivo (Decimal-safe) después
    de la resolución genérica de conflictos."""

    def __init__(self, max_variance_pct: Decimal = Decimal("50")):
        self.max_variance_pct = max_variance_pct

    def validate(
        self,
        tabla: str,
        resolved: dict,
        local: dict,
        remote: dict,
    ) -> Optional[str]:
        if tabla not in MEAT_PROCESSING_TABLES:
            return None

        if tabla == "processing_orders":
            return self._validate_order(local, remote)

        if tabla == "yield_reconciliations":
            return self._validate_yield(resolved)

        if tabla == "process_outputs":
            return self._validate_output(resolved)

        return None

    def _validate_order(self, local: dict, remote: dict) -> Optional[str]:
        # § — una orden cerrada nunca se reabre por sync remoto (mismo
        # invariante que ProcessingOrder.close() ya aplica en memoria; esto
        # es la red de seguridad para cuando el escritor remoto es un
        # dispositivo que nunca vio ese cierre).
        local_status = local.get("status", "")
        remote_status = remote.get("status", "")
        if local_status == "CLOSED" and remote_status in _OPEN_ORDER_STATUSES:
            return (
                f"Orden {local.get('id', '?')} cerrada localmente — "
                "sync remoto intentó reabrirla")
        return None

    def _validate_yield(self, resolved: dict) -> Optional[str]:
        # Réplica Decimal-safe de la regla "balance de peso sospechoso" del
        # validador legacy, sobre input_weight/actual_output_weight en vez de
        # source_weight/total_output_weight.
        input_weight = _to_decimal(resolved.get("input_weight", 0))
        actual_weight = _to_decimal(resolved.get("actual_output_weight", 0))
        if input_weight <= 0:
            return None
        variance_pct = abs(input_weight - actual_weight) / input_weight * Decimal("100")
        if variance_pct > self.max_variance_pct:
            return (
                f"Rendimiento {resolved.get('id', '?')} con variación "
                f"sospechosa ({variance_pct:.1f}%) — posible dato corrupto")
        return None

    def _validate_output(self, resolved: dict) -> Optional[str]:
        # Un output ya posteado a inventario (inventory_operation_id
        # presente) con cantidad y peso en cero es un estado que la propia
        # CHECK de process_outputs nunca permitiría insertar de forma nativa
        # — si llega así por sync, el dato ya viene corrupto de origen.
        weight = _to_decimal(resolved.get("weight", 0))
        quantity = _to_decimal(resolved.get("quantity", 0))
        if resolved.get("inventory_operation_id") and weight <= 0 and quantity <= 0:
            return (
                f"Output {resolved.get('id', '?')} posteado a inventario con "
                "peso y cantidad en cero — dato sospechoso")
        return None
