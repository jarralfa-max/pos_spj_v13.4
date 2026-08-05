"""Quality decision rules for rejection, contamination, cold chain and condemnation."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import json

from backend.domain.losses.exceptions import LossInvariantError


class QualityDecision(str, Enum):
    REJECT = "REJECT"
    CONDEMN = "CONDEMN"


class ContaminationLevel(str, Enum):
    NONE = "NONE"
    SUSPECTED = "SUSPECTED"
    CONFIRMED = "CONFIRMED"


@dataclass(frozen=True, slots=True)
class QualityEvaluation:
    decision: QualityDecision
    contamination_level: ContaminationLevel
    temperature: Decimal | None
    minimum_temperature: Decimal | None
    maximum_temperature: Decimal | None
    temperature_out_of_range: bool


def _temperature(value, field):
    if value is None: return None
    if isinstance(value, (bool, float)):
        raise LossInvariantError(f"{field} debe usar Decimal, nunca float")
    try: result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise LossInvariantError(f"{field} no es una temperatura válida") from None
    if not result.is_finite(): raise LossInvariantError(f"{field} debe ser finita")
    return result


class QualityDecisionPolicy:
    def evaluate(self, *, decision, contamination_level, evidence,
                 temperature=None, minimum_temperature=None, maximum_temperature=None):
        decision = QualityDecision(decision)
        contamination = ContaminationLevel(contamination_level)
        if not evidence:
            raise LossInvariantError("La decisión de calidad requiere evidencia")
        seen = set()
        for item in evidence:
            if not item.evidence_type.strip() or not item.storage_uri.strip():
                raise LossInvariantError("La evidencia requiere tipo y URI")
            checksum = item.checksum.strip().lower()
            if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
                raise LossInvariantError("La evidencia requiere checksum SHA-256")
            key = (item.storage_uri.strip(), checksum)
            if key in seen: raise LossInvariantError("La evidencia está duplicada")
            seen.add(key)
            try: metadata = json.loads(item.metadata_json)
            except (TypeError, json.JSONDecodeError):
                raise LossInvariantError("Los metadatos de evidencia no son JSON válido") from None
            if not isinstance(metadata, dict):
                raise LossInvariantError("Los metadatos de evidencia deben ser un objeto JSON")
        values = tuple(_temperature(value, name) for value, name in (
            (temperature, "temperature"), (minimum_temperature, "minimum_temperature"),
            (maximum_temperature, "maximum_temperature")))
        supplied = tuple(value is not None for value in values)
        if any(supplied) and not all(supplied):
            raise LossInvariantError("La lectura requiere temperatura, mínimo y máximo")
        current, minimum, maximum = values
        if minimum is not None and minimum > maximum:
            raise LossInvariantError("El rango de temperatura es inválido")
        out = current is not None and not (minimum <= current <= maximum)
        if decision is QualityDecision.CONDEMN \
                and contamination is not ContaminationLevel.CONFIRMED and not out:
            raise LossInvariantError(
                "El decomiso requiere contaminación confirmada o temperatura fuera de rango")
        return QualityEvaluation(decision, contamination, current, minimum, maximum, bool(out))
