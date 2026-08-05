"""Recovery policy for physical and financial mitigation of a loss."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from backend.domain.losses.exceptions import LossInvariantError


class RecoveryType(str, Enum):
    REWORK = "REWORK"
    RECLASSIFICATION = "RECLASSIFICATION"
    BY_PRODUCT = "BY_PRODUCT"
    CO_PRODUCT = "CO_PRODUCT"
    CLAIM = "CLAIM"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    recovery_type: RecoveryType
    quantity: Decimal
    weight: Decimal
    recovered_value: Decimal
    requires_quarantine_release: bool
    requires_inventory_reference: bool
    requires_target_product: bool


def recovery_decimal(value, field):
    if isinstance(value, (bool, float)):
        raise LossInvariantError(f"{field} debe usar Decimal, nunca float")
    try: result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise LossInvariantError(f"{field} no es decimal válido") from None
    if not result.is_finite() or result < 0:
        raise LossInvariantError(f"{field} debe ser finito y no negativo")
    return result


class LossRecoveryPolicy:
    _INVENTORY_REFERENCED = frozenset({RecoveryType.RECLASSIFICATION,
                                       RecoveryType.BY_PRODUCT, RecoveryType.CO_PRODUCT})
    _TARGETED = _INVENTORY_REFERENCED

    def plan(self, *, recovery_type, quantity, weight, recovered_value,
             gross_value, already_recovered, reference_id=None, target_product_id=None,
             quarantine_id=None, quarantine_quantity=0, quarantine_weight=0,
             loss_quantity=0, loss_weight=0, recovered_quantity=0, recovered_weight=0):
        kind = RecoveryType(recovery_type)
        qty, wgt = recovery_decimal(quantity, "quantity"), recovery_decimal(weight, "weight")
        value = recovery_decimal(recovered_value, "recovered_value")
        gross = recovery_decimal(gross_value, "gross_value")
        recovered = recovery_decimal(already_recovered, "already_recovered")
        if value <= 0: raise LossInvariantError("La recuperación requiere valor recuperado positivo")
        if recovered + value > gross:
            raise LossInvariantError("El valor recuperado excede la pérdida pendiente")
        if kind is not RecoveryType.CLAIM and qty <= 0 and wgt <= 0:
            raise LossInvariantError("La recuperación física requiere cantidad o peso")
        if kind is not RecoveryType.CLAIM:
            total_q = recovery_decimal(loss_quantity, "loss_quantity")
            total_w = recovery_decimal(loss_weight, "loss_weight")
            used_q = recovery_decimal(recovered_quantity, "recovered_quantity")
            used_w = recovery_decimal(recovered_weight, "recovered_weight")
            if (total_q > 0 and used_q + qty > total_q) or (total_w > 0 and used_w + wgt > total_w):
                raise LossInvariantError("La recuperación física excede la pérdida registrada")
        if kind is RecoveryType.REWORK and not quarantine_id:
            raise LossInvariantError("El reproceso requiere una cuarentena activa")
        if kind is RecoveryType.REWORK:
            held_q = recovery_decimal(quarantine_quantity, "quarantine_quantity")
            held_w = recovery_decimal(quarantine_weight, "quarantine_weight")
            if qty != held_q or wgt != held_w:
                raise LossInvariantError("El reproceso debe liberar la cuarentena completa")
        if (kind in self._INVENTORY_REFERENCED or kind is RecoveryType.CLAIM) and not reference_id:
            raise LossInvariantError("La recuperación requiere referencia canónica")
        if kind in self._TARGETED and not target_product_id:
            raise LossInvariantError("La recuperación requiere producto destino")
        return RecoveryPlan(kind, qty, wgt, value, kind is RecoveryType.REWORK,
                            kind in self._INVENTORY_REFERENCED,
                            kind in self._TARGETED)
