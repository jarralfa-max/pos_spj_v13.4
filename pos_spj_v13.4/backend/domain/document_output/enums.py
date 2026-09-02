"""Canonical enums for the Document Output bounded context — SET-11. See
docs/refactor/settings_refactor_execution_plan.md and the master prompt
§24-27.
"""

from __future__ import annotations

from enum import Enum


class DocumentType(str, Enum):
    """What is being printed. See §26."""

    SALE_TICKET = "SALE_TICKET"
    QUOTE = "QUOTE"
    DELIVERY_TICKET = "DELIVERY_TICKET"
    PICKING_TICKET = "PICKING_TICKET"
    ORDER_TICKET = "ORDER_TICKET"
    CASH_OPENING = "CASH_OPENING"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL"
    X_REPORT = "X_REPORT"
    Z_REPORT = "Z_REPORT"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    GOODS_RECEIPT = "GOODS_RECEIPT"
    TRANSFER_REQUEST = "TRANSFER_REQUEST"
    TRANSFER_DISPATCH = "TRANSFER_DISPATCH"
    TRANSFER_RECEIPT = "TRANSFER_RECEIPT"
    PRODUCTION_ORDER = "PRODUCTION_ORDER"
    YIELD_REPORT = "YIELD_REPORT"
    LOSS_REPORT = "LOSS_REPORT"
    DISPOSITION_CERTIFICATE = "DISPOSITION_CERTIFICATE"
    CUSTOMER_STATEMENT = "CUSTOMER_STATEMENT"
    LOYALTY_CARD = "LOYALTY_CARD"
    SWEEPSTAKES_TICKET = "SWEEPSTAKES_TICKET"
    # SET-14 "Label templates": generalizes
    # `backend/domain/inventory/enums.py::LabelType` (INV-26) — same 6
    # categories (LOT/WEIGHT/TRANSFER/COUNT/ADJUSTMENT/PRODUCT), suffixed
    # `_LABEL` here to stay distinct from the already-existing
    # TRANSFER_REQUEST/TRANSFER_DISPATCH/TRANSFER_RECEIPT ticket types
    # (transfer paperwork, not the physical box/product label).
    LOT_LABEL = "LOT_LABEL"
    WEIGHT_LABEL = "WEIGHT_LABEL"
    TRANSFER_LABEL = "TRANSFER_LABEL"
    COUNT_LABEL = "COUNT_LABEL"
    ADJUSTMENT_LABEL = "ADJUSTMENT_LABEL"
    PRODUCT_LABEL = "PRODUCT_LABEL"


LABEL_DOCUMENT_TYPES = frozenset({
    DocumentType.LOT_LABEL, DocumentType.WEIGHT_LABEL, DocumentType.TRANSFER_LABEL,
    DocumentType.COUNT_LABEL, DocumentType.ADJUSTMENT_LABEL, DocumentType.PRODUCT_LABEL,
})


class DocumentTemplateVersionStatus(str, Enum):
    """Lifecycle of one `DocumentTemplateVersion`. See §26 — exactly
    these 7 states, no REJECTED/CANCELLED/ROLLED_BACK the way
    `backend/domain/settings/enums.py::ConfigurationValueStatus` has:
    a rejected version goes back to DRAFT for revision instead."""

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class RenderFormat(str, Enum):
    """What byte/text shape a rendered document comes out as. Mirrors
    `backend/domain/device_management/enums.py::PrinterProtocol`'s "don't
    assume one format" stance, kept as a separate enum (not imported) to
    keep the two bounded contexts independent — a template rendered in
    ESC_POS is meant for a printer whose own protocol is ESC_POS, but
    that's a routing/matching concern for the caller, not a shared type."""

    ESC_POS = "ESC_POS"
    HTML = "HTML"
    PDF = "PDF"
    ZPL = "ZPL"
    VIRTUAL = "VIRTUAL"


class PrintJobStatus(str, Enum):
    """Lifecycle of one `PrintJob`. See §24."""

    PENDING = "PENDING"
    RENDERING = "RENDERING"
    READY = "READY"
    PRINTING = "PRINTING"
    PRINTED = "PRINTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DEAD_LETTER = "DEAD_LETTER"


class PrintJobPriority(str, Enum):
    """§24's "priority" field — an ordered enum rather than a bare int so
    the worker's queue-selection policy has a fixed, documented scale."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


# Most urgent first — the order `policies/print_job_queue_policy.py` uses
# to break ties between pending jobs.
PRIORITY_ORDER: tuple[PrintJobPriority, ...] = (
    PrintJobPriority.URGENT, PrintJobPriority.HIGH, PrintJobPriority.NORMAL, PrintJobPriority.LOW,
)


class DocumentSectionCode(str, Enum):
    """SET-12 "Secciones": the named, composable blocks a rendered
    document is built from. Generalizes the legacy
    `core/tickets/ticket_layout_config.py::DEFAULT_BLOCK_ORDER` block
    vocabulary (already proven against real thermal output) into a typed
    domain concept — same 13 names, not invented from scratch."""

    LOGO = "LOGO"
    BRAND_HEADER = "BRAND_HEADER"
    SALE_INFO = "SALE_INFO"
    CUSTOMER = "CUSTOMER"
    ITEMS = "ITEMS"
    TOTALS = "TOTALS"
    PAYMENT = "PAYMENT"
    LOYALTY = "LOYALTY"
    FOMO = "FOMO"
    QR = "QR"
    BARCODE = "BARCODE"
    FOOTER = "FOOTER"
    LEGAL = "LEGAL"
    # SET-15 "Boleto": generalizes the 4 sweepstakes-only block names from
    # `core/tickets/ticket_layout_config.py::RAFFLE_BLOCK_ORDER` that
    # DEFAULT_BLOCK_ORDER above doesn't already cover (RAFFLE_BLOCK_ORDER
    # otherwise reuses LOGO/BRAND_HEADER/CUSTOMER/SALE_INFO/QR/BARCODE/
    # FOOTER/LEGAL as-is).
    RAFFLE_TITLE = "RAFFLE_TITLE"
    TICKET_NUMBER = "TICKET_NUMBER"
    PRIZE = "PRIZE"
    DRAW_DATE = "DRAW_DATE"


class SectionAlignment(str, Enum):
    LEFT = "LEFT"
    CENTER = "CENTER"
    RIGHT = "RIGHT"


class MarketingMessageCategory(str, Enum):
    """SET-13 "Campaigns": generalizes the legacy
    `core/tickets/ticket_message_engine.py::TicketMessage.category`
    string ("loyalty"/"fomo"/"cta") into a typed enum — same three
    categories, not invented from scratch."""

    LOYALTY = "LOYALTY"
    FOMO = "FOMO"
    CTA = "CTA"


class RuleComparator(str, Enum):
    """SET-13 "Rules": how a `CampaignRule` compares a context metric
    against its threshold."""

    LESS_THAN = "LESS_THAN"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"
    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    EQUAL = "EQUAL"


class LabelVariableType(str, Enum):
    """SET-14 "Variables": the declared type of one placeholder a
    `LabelTemplateVariableSet` expects — lets a caller validate the data
    it supplies before rendering, rather than discovering a missing/
    wrong-shaped variable only when the printed label comes out wrong."""

    STRING = "STRING"
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    DATE = "DATE"


class SequenceResetPolicy(str, Enum):
    """SET-16 "Reset": when a `DocumentNumberSequence`'s counter rolls
    back to zero. Generalizes the implicit YEARLY behavior every existing
    ad-hoc folio scheme in this codebase already has (e.g.
    `backend/domain/procurement/value_objects.py::DocumentNumber`'s
    `PREFIX-YYYY-NNNNNN` — its counter is scoped to `WHERE document_number
    LIKE 'PREFIX-{year}-%'`, an implicit yearly reset) into an explicit,
    configurable policy."""

    NEVER = "NEVER"
    YEARLY = "YEARLY"
    MONTHLY = "MONTHLY"
    DAILY = "DAILY"
