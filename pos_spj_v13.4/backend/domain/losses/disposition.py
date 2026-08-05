"""Disposition methods, evidence integrity and double-confirmation policy."""

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from backend.domain.losses.exceptions import LossInvariantError


class DispositionMethod(str, Enum):
    AUTHORIZED_DESTRUCTION = "AUTHORIZED_DESTRUCTION"
    INCINERATION = "INCINERATION"
    LANDFILL = "LANDFILL"
    RENDERING = "RENDERING"
    COMPOSTING = "COMPOSTING"
    RETURN_TO_SUPPLIER = "RETURN_TO_SUPPLIER"
    OTHER_AUTHORIZED = "OTHER_AUTHORIZED"


CERTIFICATE_REQUIRED_METHODS = frozenset({
    DispositionMethod.AUTHORIZED_DESTRUCTION, DispositionMethod.INCINERATION,
    DispositionMethod.LANDFILL, DispositionMethod.RENDERING,
})


@dataclass(frozen=True, slots=True)
class DispositionPlan:
    method: DispositionMethod
    quantity: Decimal
    weight: Decimal
    reason: str
    certificate_required: bool


def _decimal(value, field):
    if isinstance(value, (bool, float)):
        raise LossInvariantError(f"{field} debe usar Decimal, nunca float")
    try: result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise LossInvariantError(f"{field} no es decimal válido") from None
    if not result.is_finite() or result < 0:
        raise LossInvariantError(f"{field} debe ser finito y no negativo")
    return result


class DispositionPolicy:
    def plan(self, *, method, quantity, weight, quarantine_quantity,
             quarantine_weight, reason, evidence):
        method = DispositionMethod(method)
        quantity, weight = _decimal(quantity, "quantity"), _decimal(weight, "weight")
        held_q = _decimal(quarantine_quantity, "quarantine_quantity")
        held_w = _decimal(quarantine_weight, "quarantine_weight")
        if quantity <= 0 and weight <= 0:
            raise LossInvariantError("La disposición requiere cantidad o peso")
        if quantity != held_q or weight != held_w:
            raise LossInvariantError("La disposición debe cubrir la cuarentena completa")
        if not str(reason or "").strip(): raise LossInvariantError("La disposición requiere motivo")
        self.validate_evidence(evidence)
        return DispositionPlan(method, quantity, weight, str(reason).strip(),
                               method in CERTIFICATE_REQUIRED_METHODS)

    @staticmethod
    def validate_evidence(evidence):
        if not evidence: raise LossInvariantError("La disposición requiere evidencia")
        seen = set()
        for item in evidence:
            kind, uri, checksum = item.evidence_type.strip(), item.storage_uri.strip(), item.checksum.strip().lower()
            if not kind or not uri: raise LossInvariantError("La evidencia requiere tipo y URI")
            if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
                raise LossInvariantError("La evidencia requiere checksum SHA-256")
            if (uri, checksum) in seen: raise LossInvariantError("La evidencia está duplicada")
            seen.add((uri, checksum))
            try: metadata = json.loads(item.metadata_json)
            except (TypeError, json.JSONDecodeError):
                raise LossInvariantError("Los metadatos de evidencia no son JSON válido") from None
            if not isinstance(metadata, dict):
                raise LossInvariantError("Los metadatos deben ser un objeto JSON")

    @staticmethod
    def validate_completion(*, certificate_required, certificate_reference, evidence):
        DispositionPolicy.validate_evidence(evidence)
        if certificate_required and not str(certificate_reference or "").strip():
            raise LossInvariantError("El método requiere certificado de disposición")
