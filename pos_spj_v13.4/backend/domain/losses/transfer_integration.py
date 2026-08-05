"""Pure policies for converting confirmed transfer discrepancies into losses."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from backend.domain.losses.enums import LossClassificationCode
from backend.domain.losses.exceptions import LossInvariantError


class ClaimPartyType(str, Enum):
    CARRIER = "CARRIER"
    ORIGIN_BRANCH = "ORIGIN_BRANCH"
    DESTINATION_BRANCH = "DESTINATION_BRANCH"
    EMPLOYEE = "EMPLOYEE"
    SUPPLIER = "SUPPLIER"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class TransferLossAssessment:
    classification: LossClassificationCode
    loss_quantity: Decimal
    loss_weight: Decimal
    responsible_stage: str
    suggested_party_type: ClaimPartyType


def decimal_value(value, field):
    if isinstance(value, (bool, float)):
        raise LossInvariantError(f"{field} debe usar Decimal, nunca float")
    try: result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise LossInvariantError(f"{field} no es decimal válido") from None
    if not result.is_finite() or result < 0:
        raise LossInvariantError(f"{field} debe ser finito y no negativo")
    return result


class TransferLossPolicy:
    _CLASSIFICATIONS = {
        "SHORT_QUANTITY": LossClassificationCode.TRANSFER_DIFFERENCE,
        "WEIGHT_VARIANCE": LossClassificationCode.TRANSFER_DIFFERENCE,
        "PACKAGE_MISSING": LossClassificationCode.TRANSFER_DIFFERENCE,
        "LOST_IN_TRANSIT": LossClassificationCode.TRANSFER_DIFFERENCE,
        "DAMAGED": LossClassificationCode.TRANSPORT_DAMAGE,
        "TEMPERATURE_VARIANCE": LossClassificationCode.TEMPERATURE_EXCURSION,
        "EXPIRED": LossClassificationCode.EXPIRY,
        "QUALITY_FAILURE": LossClassificationCode.QUALITY_REJECTION,
    }
    _PARTIES = {"TRANSIT": ClaimPartyType.CARRIER, "DISPATCH": ClaimPartyType.ORIGIN_BRANCH,
                "PICKING": ClaimPartyType.ORIGIN_BRANCH,
                "RECEIVING": ClaimPartyType.DESTINATION_BRANCH}

    def assess(self, *, difference_type, expected_quantity, actual_quantity,
               expected_weight, actual_weight, responsible_stage):
        kind = str(difference_type or "").strip().upper()
        if kind == "OVER_QUANTITY":
            raise LossInvariantError("Un sobrante no puede registrarse como pérdida")
        classification = self._CLASSIFICATIONS.get(kind)
        if classification is None:
            raise LossInvariantError(f"La diferencia {kind} no genera un expediente de pérdida")
        expected_q = decimal_value(expected_quantity, "expected_quantity")
        actual_q = decimal_value(actual_quantity, "actual_quantity")
        expected_w = decimal_value(expected_weight, "expected_weight")
        actual_w = decimal_value(actual_weight, "actual_weight")
        if kind in {"SHORT_QUANTITY", "WEIGHT_VARIANCE", "PACKAGE_MISSING", "LOST_IN_TRANSIT"}:
            quantity, weight = max(Decimal("0"), expected_q - actual_q), max(Decimal("0"), expected_w - actual_w)
        else:
            quantity, weight = actual_q, actual_w
        if quantity <= 0 and weight <= 0:
            raise LossInvariantError("La diferencia no contiene una pérdida positiva")
        stage = str(responsible_stage or "").strip().upper()
        if not stage: raise LossInvariantError("La diferencia requiere etapa responsable")
        return TransferLossAssessment(classification, quantity, weight, stage,
                                      self._PARTIES.get(stage, ClaimPartyType.OTHER))
