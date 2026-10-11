"""Esquema de Cotizaciones (CRM-43, migración 318).

Reemplaza a la tabla legacy ``cotizaciones`` (identidad ``cliente_id`` de la
tabla ``clientes``, sin escritor desde que se retiró ``CotizacionService``).
Importes y cantidades como TEXT decimal, igual que Pedidos y Crédito.
"""

from __future__ import annotations

QUOTES_TABLES = ("quotes", "quote_lines", "quote_audit_log", "quote_outbox")

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS quotes (
        id TEXT NOT NULL PRIMARY KEY,
        quote_number TEXT NOT NULL UNIQUE,
        revision INTEGER NOT NULL DEFAULT 1,
        parent_quote_id TEXT REFERENCES quotes(id),
        customer_id TEXT NOT NULL,
        opportunity_id TEXT,
        branch_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
            'DRAFT','PENDING_APPROVAL','APPROVED','SENT','ACCEPTED','REJECTED',
            'EXPIRED','CANCELLED','CONVERTED')),
        valid_until TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'MXN',
        notes TEXT NOT NULL DEFAULT '',
        internal_notes TEXT NOT NULL DEFAULT '',
        list_subtotal TEXT NOT NULL DEFAULT '0',
        discount_total TEXT NOT NULL DEFAULT '0',
        total TEXT NOT NULL DEFAULT '0',
        requires_approval INTEGER NOT NULL DEFAULT 0,
        created_by_user_id TEXT NOT NULL,
        submitted_at TEXT,
        approved_by_user_id TEXT,
        approved_at TEXT,
        approval_note TEXT NOT NULL DEFAULT '',
        sent_at TEXT,
        accepted_at TEXT,
        rejected_at TEXT,
        reject_reason TEXT NOT NULL DEFAULT '',
        cancelled_at TEXT,
        cancel_reason TEXT NOT NULL DEFAULT '',
        expired_at TEXT,
        converted_order_id TEXT,
        converted_at TEXT,
        legacy_quote_id TEXT UNIQUE,
        version INTEGER NOT NULL DEFAULT 1,
        operation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quote_lines (
        id TEXT NOT NULL PRIMARY KEY,
        quote_id TEXT NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
        line_number INTEGER NOT NULL,
        product_id TEXT NOT NULL,
        product_code TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL,
        unit_code TEXT NOT NULL DEFAULT '',
        weighed INTEGER NOT NULL DEFAULT 0,
        quantity TEXT NOT NULL,
        list_price TEXT NOT NULL,
        unit_price TEXT NOT NULL,
        min_price TEXT,
        line_total TEXT NOT NULL,
        notes TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quote_audit_log (
        id TEXT NOT NULL PRIMARY KEY,
        quote_id TEXT NOT NULL,
        action TEXT NOT NULL,
        actor_user_id TEXT,
        detail TEXT NOT NULL DEFAULT '',
        operation_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quote_outbox (
        id TEXT NOT NULL PRIMARY KEY,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT,
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_quotes_customer ON quotes(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_quotes_opportunity ON quotes(opportunity_id)",
    "CREATE INDEX IF NOT EXISTS idx_quotes_status ON quotes(status, valid_until)",
    "CREATE INDEX IF NOT EXISTS idx_quotes_branch ON quotes(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_quote_lines_quote ON quote_lines(quote_id)",
    "CREATE INDEX IF NOT EXISTS idx_quote_audit_quote ON quote_audit_log(quote_id)",
)


def create_quotes_schema(conn) -> None:
    for ddl in _DDL:
        conn.execute(ddl)
    for ddl in _INDEXES:
        conn.execute(ddl)
