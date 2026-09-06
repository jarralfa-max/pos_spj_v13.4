"""Canonical WhatsApp channel schema (WA-3, prompt maestro §9/§14-15/§19-21/§61).

Backs the pure-domain entities built in WA-2
(``whatsapp_service/domain/whatsapp/entities/``) plus the cross-cutting
infrastructure the master prompt requires for the channel: a single inbox,
a single outbox, business-operation idempotency, and dead letter.

Design notes (same conventions already established by
``orders_delivery_schema.py`` / ``loyalty_schema.py``):

- Every PK is ``TEXT`` (UUIDv7, REGLA CERO) — never ``INTEGER AUTOINCREMENT``.
- Status/enum values are NOT enforced via SQL ``CHECK`` — the domain layer
  (``whatsapp_service/domain/whatsapp/enums.py`` + entities) is the single
  source of truth for valid values and transitions, matching this repo's
  established convention (``sales_schema.py``/``loyalty_schema.py`` have
  zero enum ``CHECK`` constraints either).
- Structural idempotency: ``UNIQUE(operation_id)`` on ``whatsapp_outbox``
  and ``whatsapp_business_operation_idempotency``, plus
  ``UNIQUE(fingerprint)`` on the idempotency table itself (the actual
  "was this business action already requested, even under a different
  message wording" dedup key per prompt maestro §19).
- ``whatsapp_business_operation_idempotency`` and ``whatsapp_outbox`` are
  genuinely NEW capabilities, not a rename of anything existing —
  ``docs/refactor/whatsapp_schema_consolidation.md`` §2 found the official
  microservice sends messages synchronously with no persisted outbox at
  all (a real "single sender/single outbox" gap vs. the master prompt), and
  §3 found the existing ``wa_business_idempotency`` (created in code, not a
  migration, with an ``INTEGER AUTOINCREMENT`` PK) is a different, narrower
  shape than the ``operation_id``/``aggregate_type``/``fingerprint``
  design §19 asks for.

Deliberately does NOT touch, rename, or drop any legacy WhatsApp table
(``whatsapp_numeros``, ``wa_event_log``, ``wa_business_idempotency``,
``whatsapp_queue``, ``pedidos_whatsapp*``, ``conversations``/``message_log``
created in ``whatsapp_service/state/conversation.py``, etc. — full inventory
in ``docs/refactor/whatsapp_legacy_inventory.md`` and
``docs/refactor/whatsapp_schema_consolidation.md``). Those tables have real,
currently-live consumers; migrating/retiring them is separate, later work
gated on "confirm zero consumers first" (prompt maestro §74), and — for the
``pedidos_whatsapp*`` pair specifically — on a still-open product decision
about which of the three parallel WhatsApp ordering pipelines is
authoritative (``whatsapp_legacy_inventory.md``, 5 BLOCKED items). This
migration only adds the NEW canonical schema for the bounded-context
rebuild; nothing reads or writes it yet (that wiring is WA-4 bootstrap +
WA-9 ERP contracts) — same "parallel, not-yet-wired domain" relationship
``orders_delivery_schema.py`` already has with ``pedidos_whatsapp*``/
``delivery_orders``.

Only a migration in ``migrations/`` may execute this DDL.
"""
from __future__ import annotations

WHATSAPP_TABLES = (
    "whatsapp_business_accounts",
    "whatsapp_provider_configurations",
    "whatsapp_channel_numbers",
    "whatsapp_identities",
    "whatsapp_conversations",
    "whatsapp_conversation_sessions",
    "whatsapp_messages",
    "whatsapp_message_deliveries",
    "whatsapp_inbox",
    "whatsapp_outbox",
    "whatsapp_business_operation_idempotency",
    "whatsapp_dead_letter",
    "whatsapp_order_drafts",
    "whatsapp_order_draft_lines",
    "whatsapp_quote_drafts",
    "whatsapp_quote_draft_lines",
    "whatsapp_delivery_requests",
    "whatsapp_handoff_requests",
)

_DDL = (
    # ── Accounts (WhatsAppBusinessAccount, §10) ─────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_business_accounts (
        id TEXT NOT NULL PRIMARY KEY,
        provider TEXT NOT NULL,
        business_account_external_id TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        secret_reference_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── Provider configuration (WhatsAppProviderConfiguration, §10) ────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_provider_configurations (
        id TEXT NOT NULL PRIMARY KEY,
        account_id TEXT NOT NULL UNIQUE REFERENCES whatsapp_business_accounts(id),
        provider TEXT NOT NULL,
        api_version TEXT NOT NULL,
        extra_settings_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── Numbers (WhatsAppChannelNumber, §10-11) ─────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_channel_numbers (
        id TEXT NOT NULL PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES whatsapp_business_accounts(id),
        phone_number_external_id TEXT NOT NULL UNIQUE,
        display_phone_number TEXT NOT NULL,
        normalized_phone_number TEXT NOT NULL,
        branch_id TEXT,
        channel_role TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        timezone TEXT NOT NULL,
        locale TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── Identity (WhatsAppIdentity, §12) ────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_identities (
        id TEXT NOT NULL PRIMARY KEY,
        wa_id TEXT NOT NULL UNIQUE,
        normalized_phone TEXT NOT NULL,
        customer_id TEXT,
        identity_status TEXT NOT NULL DEFAULT 'UNRESOLVED',
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        blocked_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── Conversation (WhatsAppConversation + ConversationContext, §14/§31) ─
    """
    CREATE TABLE IF NOT EXISTS whatsapp_conversations (
        id TEXT NOT NULL PRIMARY KEY,
        identity_id TEXT NOT NULL REFERENCES whatsapp_identities(id),
        channel_number_id TEXT NOT NULL REFERENCES whatsapp_channel_numbers(id),
        branch_id TEXT,
        state TEXT NOT NULL DEFAULT 'OPEN',
        context_json TEXT NOT NULL DEFAULT '{}',
        context_version INTEGER NOT NULL DEFAULT 1,
        current_session_id TEXT,
        opened_at TEXT NOT NULL,
        closed_at TEXT,
        last_message_at TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    # ── ConversationSession (§14) ────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_conversation_sessions (
        id TEXT NOT NULL PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES whatsapp_conversations(id),
        started_at TEXT NOT NULL,
        ended_at TEXT
    )
    """,
    # ── Message (WhatsAppMessage, §15) ──────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_messages (
        id TEXT NOT NULL PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES whatsapp_conversations(id),
        direction TEXT NOT NULL,
        message_type TEXT NOT NULL,
        provider_message_id TEXT UNIQUE,
        payload_reference TEXT,
        correlation_id TEXT,
        operation_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    # ── MessageDelivery (WhatsAppMessageDelivery, §15) ──────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_message_deliveries (
        id TEXT NOT NULL PRIMARY KEY,
        message_id TEXT NOT NULL UNIQUE REFERENCES whatsapp_messages(id),
        status TEXT NOT NULL DEFAULT 'QUEUED',
        sent_at TEXT,
        delivered_at TEXT,
        read_at TEXT,
        failed_at TEXT,
        error_code TEXT,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )
    """,
    # ── Inbox (§20-21 — InboundMessageJob) ──────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_inbox (
        id TEXT NOT NULL PRIMARY KEY,
        message_id TEXT NOT NULL UNIQUE REFERENCES whatsapp_messages(id),
        status TEXT NOT NULL DEFAULT 'PENDING',
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        locked_at TEXT,
        created_at TEXT NOT NULL,
        processed_at TEXT
    )
    """,
    # ── Outbox (§21-22 — the "no persisted outbox" gap the audit flagged) ──
    """
    CREATE TABLE IF NOT EXISTS whatsapp_outbox (
        id TEXT NOT NULL PRIMARY KEY,
        message_id TEXT REFERENCES whatsapp_messages(id),
        conversation_id TEXT REFERENCES whatsapp_conversations(id),
        channel_number_id TEXT REFERENCES whatsapp_channel_numbers(id),
        destination_phone TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        template_name TEXT,
        operation_id TEXT UNIQUE,
        status TEXT NOT NULL DEFAULT 'PENDING',
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        next_retry_at TEXT,
        created_at TEXT NOT NULL,
        processed_at TEXT
    )
    """,
    # ── Business operation idempotency (§19) ────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_business_operation_idempotency (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE,
        operation_type TEXT NOT NULL,
        aggregate_type TEXT NOT NULL,
        aggregate_id TEXT,
        fingerprint TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'PENDING',
        result_reference TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    # ── Dead letter (§61) ────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_dead_letter (
        id TEXT NOT NULL PRIMARY KEY,
        message_id TEXT REFERENCES whatsapp_messages(id),
        operation_id TEXT,
        failure_type TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        payload_reference TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        resolved_by TEXT,
        resolution TEXT
    )
    """,
    # ── OrderDraft (WA-10, §34-35 — el carrito conversacional, nunca el
    # pedido canónico) ───────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_order_drafts (
        id TEXT NOT NULL PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES whatsapp_conversations(id),
        branch_id TEXT,
        customer_external_id TEXT,
        delivery_method TEXT,
        status TEXT NOT NULL DEFAULT 'BUILDING',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS whatsapp_order_draft_lines (
        id TEXT NOT NULL PRIMARY KEY,
        draft_id TEXT NOT NULL REFERENCES whatsapp_order_drafts(id),
        product_external_id TEXT NOT NULL,
        product_name TEXT NOT NULL,
        quantity TEXT NOT NULL,
        unit TEXT NOT NULL,
        unit_price TEXT NOT NULL
    )
    """,
    # ── QuoteDraft (WA-11, §37) ──────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_quote_drafts (
        id TEXT NOT NULL PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES whatsapp_conversations(id),
        branch_id TEXT,
        customer_external_id TEXT,
        quote_external_id TEXT,
        folio TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'CAPTURING',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS whatsapp_quote_draft_lines (
        id TEXT NOT NULL PRIMARY KEY,
        draft_id TEXT NOT NULL REFERENCES whatsapp_quote_drafts(id),
        product_external_id TEXT NOT NULL,
        product_name TEXT NOT NULL,
        quantity TEXT NOT NULL,
        unit TEXT NOT NULL,
        unit_price TEXT NOT NULL
    )
    """,
    # ── DeliveryRequest (WA-13) — rastro conversacional de "programar
    # entrega para el pedido X"; el estado operativo real de la entrega
    # sigue siendo propiedad de Orders/Delivery, no de este canal ─────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_delivery_requests (
        id TEXT NOT NULL PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES whatsapp_conversations(id),
        order_external_id TEXT NOT NULL,
        address TEXT NOT NULL,
        delivery_date TEXT,
        customer_phone TEXT,
        status TEXT NOT NULL DEFAULT 'REQUESTED',
        failure_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── HandoffRequest (WA-16, §32) — solicitud de traspaso a un agente
    # humano; distinta de ConversationState.HANDOFF_REQUESTED/HUMAN_ACTIVE
    # (WA-2/WA-7), que es el estado de la conversación en sí ───────────────
    """
    CREATE TABLE IF NOT EXISTS whatsapp_handoff_requests (
        id TEXT NOT NULL PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES whatsapp_conversations(id),
        branch_id TEXT,
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        assigned_to_phone TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        resolved_at TEXT
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_channel_numbers_account"
    " ON whatsapp_channel_numbers(account_id)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_channel_numbers_branch"
    " ON whatsapp_channel_numbers(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_identities_phone"
    " ON whatsapp_identities(normalized_phone)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_identities_customer"
    " ON whatsapp_identities(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_conversations_identity"
    " ON whatsapp_conversations(identity_id, channel_number_id)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_conversations_state"
    " ON whatsapp_conversations(state)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_conversation_sessions_conversation"
    " ON whatsapp_conversation_sessions(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_conversation"
    " ON whatsapp_messages(conversation_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_message_deliveries_status"
    " ON whatsapp_message_deliveries(status)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_inbox_status"
    " ON whatsapp_inbox(status)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_outbox_status"
    " ON whatsapp_outbox(status, next_retry_at)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_idempotency_aggregate"
    " ON whatsapp_business_operation_idempotency(aggregate_type, aggregate_id)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_dead_letter_unresolved"
    " ON whatsapp_dead_letter(resolved_at)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_order_drafts_conversation"
    " ON whatsapp_order_drafts(conversation_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_order_draft_lines_draft"
    " ON whatsapp_order_draft_lines(draft_id)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_quote_drafts_conversation"
    " ON whatsapp_quote_drafts(conversation_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_quote_draft_lines_draft"
    " ON whatsapp_quote_draft_lines(draft_id)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_delivery_requests_order"
    " ON whatsapp_delivery_requests(order_external_id)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_handoff_requests_conversation"
    " ON whatsapp_handoff_requests(conversation_id, status)",
)


def create_whatsapp_schema(conn) -> None:
    """Create the canonical WhatsApp channel schema (idempotent). DDL lives
    only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_whatsapp_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(WHATSAPP_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
