"""Slaughter preparation vocabulary (§37/§50, PROC-24). Not persisted, not
enforced anywhere yet — the vocabulary the future contracts speak, defined
now so the contracts below are typed rather than free strings."""

from enum import Enum


class AnimalLotStatus(str, Enum):
    RECEIVED = "RECEIVED"
    IN_HOLDING = "IN_HOLDING"
    APPROVED_FOR_SLAUGHTER = "APPROVED_FOR_SLAUGHTER"
    REJECTED = "REJECTED"


class SlaughterOrderStatus(str, Enum):
    """Small subset of ProcessingOrderStatus's vocabulary (§13) — a full
    15-state lifecycle would be premature for a flow with no execution
    engine yet."""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class AnteMortemDisposition(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CONDITIONAL = "CONDITIONAL"


class PostMortemDisposition(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL_CONDEMNATION = "PARTIAL_CONDEMNATION"
    TOTAL_CONDEMNATION = "TOTAL_CONDEMNATION"
