"""LOSS-15 investigation invariants and immutable evidence validation."""

import json
from datetime import datetime, timezone

from backend.domain.losses.exceptions import LossInvariantError


class InvestigationPolicy:
    OPENABLE_CASE_STATES = frozenset({"SUBMITTED", "UNDER_REVIEW", "APPROVED",
                                      "INVENTORY_POSTED", "TREATMENT_PENDING", "CLOSED"})

    @staticmethod
    def validate_open(*, case_status, assigned_to_user_id, due_at, reason):
        if case_status not in InvestigationPolicy.OPENABLE_CASE_STATES:
            raise LossInvariantError("El expediente no admite investigación")
        if not str(assigned_to_user_id or "").strip():
            raise LossInvariantError("La investigación requiere responsable")
        if due_at.tzinfo is None or due_at.utcoffset() is None:
            raise LossInvariantError("La fecha límite debe incluir zona horaria")
        if due_at.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            raise LossInvariantError("La fecha límite debe ser futura")
        if not str(reason or "").strip():
            raise LossInvariantError("La apertura requiere motivo")

    @staticmethod
    def validate_evidence(items):
        if not items: raise LossInvariantError("La operación requiere evidencia")
        seen = set()
        for item in items:
            kind, uri, checksum = item.evidence_type.strip(), item.storage_uri.strip(), item.checksum.strip().lower()
            if not kind or not uri: raise LossInvariantError("La evidencia requiere tipo y URI")
            if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
                raise LossInvariantError("La evidencia requiere checksum SHA-256")
            if (uri, checksum) in seen: raise LossInvariantError("La evidencia está duplicada")
            seen.add((uri, checksum))
            try: metadata = json.loads(item.metadata_json)
            except (TypeError, json.JSONDecodeError):
                raise LossInvariantError("Los metadatos no son JSON válido") from None
            if not isinstance(metadata, dict): raise LossInvariantError("Los metadatos deben ser un objeto JSON")

    @staticmethod
    def validate_finding(*, cause_code, description, evidence):
        if not str(cause_code or "").strip() or not str(description or "").strip():
            raise LossInvariantError("El hallazgo requiere causa y descripción")
        InvestigationPolicy.validate_evidence(evidence)

    @staticmethod
    def validate_conclusion(*, finding_count, conclusion, evidence):
        if int(finding_count) < 1: raise LossInvariantError("La conclusión requiere hallazgos")
        if not str(conclusion or "").strip(): raise LossInvariantError("La conclusión es obligatoria")
        InvestigationPolicy.validate_evidence(evidence)
