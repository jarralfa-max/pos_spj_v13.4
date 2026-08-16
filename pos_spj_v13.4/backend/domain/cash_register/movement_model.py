"""Canonical Cash Register movement contract.

Cash balance is reconstructed from immutable ledger entries, but not every
``movement_type``/``direction`` pair is valid.  This module is the single domain
source for that contract so use cases, tests and future APIs do not spread cash
movement rules as ad-hoc dictionaries.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.domain.cash_register.enums import CashMovementDirection, CashMovementType
from backend.domain.cash_register.exceptions import CashInvalidStateError


INFLOW_MOVEMENT_TYPES = frozenset({
    CashMovementType.OPENING_FLOAT,
    CashMovementType.CASH_SALE,
    CashMovementType.CASH_IN,
    CashMovementType.MANUAL_INCOME,
    CashMovementType.CASH_RECEIPT,
    CashMovementType.CHANGE_ADDITION,
})

OUTFLOW_MOVEMENT_TYPES = frozenset({
    CashMovementType.CASH_REFUND,
    CashMovementType.CASH_OUT,
    CashMovementType.MANUAL_WITHDRAWAL,
    CashMovementType.SAFE_DROP,
    CashMovementType.CASH_PICKUP,
    CashMovementType.CASH_HANDOVER,
    CashMovementType.AUTHORIZED_PAID_OUT,
})

FLEXIBLE_DIRECTION_MOVEMENT_TYPES = frozenset({
    CashMovementType.ADJUSTMENT,
    CashMovementType.REVERSAL,
})

SOURCE_DOCUMENT_REQUIRED_TYPES = frozenset({
    CashMovementType.OPENING_FLOAT,
    CashMovementType.CASH_SALE,
    CashMovementType.CASH_REFUND,
    CashMovementType.SAFE_DROP,
    CashMovementType.CASH_PICKUP,
    CashMovementType.CASH_HANDOVER,
    CashMovementType.CASH_RECEIPT,
})

CONCEPT_REQUIRED_TYPES = frozenset({
    CashMovementType.MANUAL_INCOME,
    CashMovementType.MANUAL_WITHDRAWAL,
    CashMovementType.SAFE_DROP,
    CashMovementType.CASH_IN,
    CashMovementType.CASH_OUT,
    CashMovementType.CASH_PICKUP,
    CashMovementType.CASH_HANDOVER,
    CashMovementType.AUTHORIZED_PAID_OUT,
    CashMovementType.ADJUSTMENT,
    CashMovementType.REVERSAL,
})


def canonical_direction(movement_type: CashMovementType) -> CashMovementDirection | None:
    if movement_type in INFLOW_MOVEMENT_TYPES:
        return CashMovementDirection.INFLOW
    if movement_type in OUTFLOW_MOVEMENT_TYPES:
        return CashMovementDirection.OUTFLOW
    if movement_type in FLEXIBLE_DIRECTION_MOVEMENT_TYPES:
        return None
    raise CashInvalidStateError(f"Tipo de movimiento de Caja no canónico: {movement_type!r}")


@dataclass(frozen=True, slots=True)
class CashMovementContract:
    movement_type: CashMovementType
    direction: CashMovementDirection
    requires_source_document: bool
    requires_concept: bool
    is_reversal: bool


def resolve_movement_contract(
    movement_type: CashMovementType,
    direction: CashMovementDirection,
) -> CashMovementContract:
    expected = canonical_direction(movement_type)
    if expected is not None and direction is not expected:
        raise CashInvalidStateError(
            f"{movement_type.value} debe registrarse con dirección {expected.value}"
        )
    return CashMovementContract(
        movement_type=movement_type,
        direction=direction,
        requires_source_document=movement_type in SOURCE_DOCUMENT_REQUIRED_TYPES,
        requires_concept=movement_type in CONCEPT_REQUIRED_TYPES,
        is_reversal=movement_type is CashMovementType.REVERSAL,
    )


def ensure_cash_movement_contract(
    *,
    movement_type: CashMovementType,
    direction: CashMovementDirection,
    concept: str,
    reference_id: str | None,
    reversal_of_id: str | None,
) -> CashMovementContract:
    contract = resolve_movement_contract(movement_type, direction)
    if contract.requires_concept and not concept.strip():
        raise CashInvalidStateError("El movimiento de Caja requiere concepto operativo")
    if contract.requires_source_document and not reference_id:
        raise CashInvalidStateError("El movimiento de Caja requiere documento origen")
    if contract.is_reversal:
        if not reversal_of_id:
            raise CashInvalidStateError("El reverso requiere el movimiento original")
    elif reversal_of_id is not None:
        raise CashInvalidStateError("Solo un reverso puede referenciar reversal_of_id")
    return contract
