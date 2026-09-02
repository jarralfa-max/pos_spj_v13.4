"""Canonical enums for the Loyalty Cards bounded context (LOY-16, master
prompt §31-32)."""

from __future__ import annotations

from enum import Enum


class LoyaltyCardType(str, Enum):
    PHYSICAL = "PHYSICAL"
    DIGITAL = "DIGITAL"


class LoyaltyCardStatus(str, Enum):
    """§31. ``ISSUED`` = printed/provisioned but not yet handed to the
    customer and activated; a card only earns/redeems once ``ACTIVE``."""
    ISSUED = "ISSUED"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    REPLACED = "REPLACED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class LoyaltyCardTokenStatus(str, Enum):
    """§32 — QR público rotable sin cambiar el id interno de la tarjeta."""
    ACTIVE = "ACTIVE"
    ROTATED = "ROTATED"
    REVOKED = "REVOKED"


class LoyaltyCardTemplateTargetType(str, Enum):
    """§33 — a template's design may target a physical card, a digital
    wallet card, or both."""
    PHYSICAL = "PHYSICAL"
    DIGITAL = "DIGITAL"
    BOTH = "BOTH"


class LoyaltyCardTemplateStatus(str, Enum):
    """§33 — governs whether the template is available for card issuance/
    batches at all (business-level approval), independent of which specific
    design snapshot is live (see `LoyaltyCardTemplateVersionStatus`)."""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class LoyaltyCardTemplateVersionStatus(str, Enum):
    """§33 — governs which design snapshot is currently live. A template
    may accumulate many versions over time; only one may be ACTIVE."""
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class SheetOrientation(str, Enum):
    """§38-40."""
    PORTRAIT = "PORTRAIT"
    LANDSCAPE = "LANDSCAPE"


class LoyaltyCardBatchStatus(str, Enum):
    """§43-44."""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PRINTING = "PRINTING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class LoyaltyCardBatchItemStatus(str, Enum):
    """§43-44."""
    PENDING = "PENDING"
    PRINTED = "PRINTED"
    FAILED = "FAILED"


class LoyaltyCardPrintJobStatus(str, Enum):
    """§50-51. Deliberately mirrors the shape of
    `backend.domain.document_output.entities.print_job.PrintJob`'s own
    status machine (PENDING→RENDERING→READY, FAILED) for consistency, but
    is its OWN entity in its OWN schema — see
    `loyalty_card_print_job.py`'s docstring for why reusing that entity's
    table directly turned out not to be possible."""
    PENDING = "PENDING"
    RENDERING = "RENDERING"
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
