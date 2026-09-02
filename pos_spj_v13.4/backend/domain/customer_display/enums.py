"""Canonical enums for the Customer Display bounded context — SET-17.
See docs/refactor/settings_refactor_execution_plan.md and the master
prompt's Configuración/Customer Display scope.
"""

from __future__ import annotations

from enum import Enum


class CustomerDisplayMode(str, Enum):
    """"Modes": what a customer-facing second screen is currently
    showing. Generalizes the legacy string vocabulary
    `backend/application/sales/queries/customer_display_query_service.py::
    _SCREEN_BY_STATUS` already maps every `SaleStatus` onto ("CART",
    "IDLE", "PAYMENT_PENDING", "THANK_YOU") — same 4 values, not
    invented from scratch. Sales only *publishes* state for this screen,
    never controls it (§6/§50) — this bounded context owns the screen's
    identity/layout/mode, never sale business logic."""

    IDLE = "IDLE"
    CART = "CART"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    THANK_YOU = "THANK_YOU"


class CustomerDisplaySectionCode(str, Enum):
    """"Layouts": the named, composable blocks a `DisplayLayout` can
    show for its mode. Independently defined from
    `backend.domain.document_output.enums.DocumentSectionCode` — same
    bounded-context-independence discipline as everywhere else in this
    refactor, not a shared/imported vocabulary — even though a few names
    overlap in spirit (both have a "totals" concept, but a printed ticket
    and a live screen are different content surfaces)."""

    CUSTOMER_NAME = "CUSTOMER_NAME"
    ITEMS = "ITEMS"
    SUBTOTAL = "SUBTOTAL"
    DISCOUNT = "DISCOUNT"
    TOTAL = "TOTAL"
    MESSAGE = "MESSAGE"
    LOGO = "LOGO"


class ContentType(str, Enum):
    """SET-18 "Content": the shape of one piece of advertising/idle-screen
    content. `body` is interpreted per type — a plain message for TEXT, a
    reference/URL/base64 payload for IMAGE/VIDEO, markup for HTML — this
    bounded context never renders it, the same "carries no printer bytes"
    discipline `backend.domain.document_output.value_objects.
    ticket_data.TicketData` already established for tickets."""

    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    TEXT = "TEXT"
    HTML = "HTML"


class ContentCampaignStatus(str, Enum):
    """SET-18 "Approval": lifecycle of one `ContentCampaign`. Mirrors
    `backend.domain.document_output.enums.DocumentTemplateVersionStatus`'s
    exact 7-state shape (SET-11) — the same "needs review before it's
    live" discipline applies to advertising content shown on a
    customer-facing screen as to a printed document template; no
    REJECTED terminal state here either, a rejected campaign goes back to
    DRAFT for revision."""

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"
