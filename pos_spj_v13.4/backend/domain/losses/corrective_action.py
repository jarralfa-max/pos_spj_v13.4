"""Corrective-action lifecycle invariants for LOSS-17."""
from datetime import datetime,timezone
from enum import Enum
from backend.domain.losses.exceptions import LossInvariantError
class EffectivenessDecision(str,Enum):
    EFFECTIVE="EFFECTIVE"
    INEFFECTIVE="INEFFECTIVE"
class CorrectiveActionPolicy:
    TERMINAL_STATES = frozenset({"EFFECTIVE","INEFFECTIVE","CANCELLED"})
    @staticmethod
    def validate_create(*,title,description,owner_user_id,due_at):
        if not str(title or "").strip() or not str(description or "").strip(): raise LossInvariantError("La acción requiere título y descripción")
        if not str(owner_user_id or "").strip(): raise LossInvariantError("La acción requiere responsable")
        if due_at.tzinfo is None or due_at.utcoffset() is None: raise LossInvariantError("El vencimiento debe incluir zona horaria")
        if due_at.astimezone(timezone.utc)<=datetime.now(timezone.utc): raise LossInvariantError("El vencimiento debe ser futuro")
    @staticmethod
    def validate_submission(*,notes,evidence_uri,checksum):
        if not str(notes or "").strip() or not str(evidence_uri or "").strip(): raise LossInvariantError("La ejecución requiere notas y evidencia")
        checksum=str(checksum or "").lower()
        if len(checksum)!=64 or any(c not in "0123456789abcdef" for c in checksum): raise LossInvariantError("La evidencia requiere checksum SHA-256")
    @staticmethod
    def validate_verification(*,decision,notes):
        try: EffectivenessDecision(decision)
        except ValueError: raise LossInvariantError("Decisión de efectividad inválida") from None
        if not str(notes or "").strip(): raise LossInvariantError("La verificación requiere observaciones")
    @staticmethod
    def is_overdue(*,due_at,status,as_of=None):
        if due_at.tzinfo is None or due_at.utcoffset() is None: raise LossInvariantError("El vencimiento debe incluir zona horaria")
        reference=as_of or datetime.now(timezone.utc)
        if reference.tzinfo is None or reference.utcoffset() is None: raise LossInvariantError("La fecha de consulta debe incluir zona horaria")
        return status not in CorrectiveActionPolicy.TERMINAL_STATES and due_at.astimezone(timezone.utc)<reference.astimezone(timezone.utc)
