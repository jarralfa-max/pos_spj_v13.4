"""p004 — Proyecciones centrales de Caja, Finanzas, Crédito y Fidelidad
(arquitectura híbrida, Slice 6).

Igual que Ventas e Inventario (p003): se construyen desde el libro de hechos y
guardan lo que cada estación decidió, sin recalcular reglas.

* Caja: turnos, movimientos con importe FIRMADO (entrada +, salida −; la reversa
  es el inverso del original), cortes Z con esperado/contado/diferencia.
* Finanzas: asientos con sus renglones (cuenta por código y tipo, porque el id
  es de cada instalación). Un asiento que no cuadra NO se proyecta (queda en
  ERROR, visible). Vistas `central_trial_balance` (balanza por sucursal y
  cuenta) y `central_receivables` (saldo por cobrar por cliente).
* Crédito: cuenta de crédito por cliente (límite y estado) y la vista
  `central_credit_exposure`: límite, saldo por cobrar consolidado de TODAS las
  sucursales y disponible. Es la exposición real que una sucursal sola no ve.
* Fidelidad: una fila por TRANSACCIÓN del libro de puntos (no por evento: la
  confirmación de una reserva no suma otra vez) y la vista
  `central_loyalty_balances`, con la misma regla de saldo de la estación.

`NUMERIC` sin escala fija, como en p003. Idempotente.
"""

from __future__ import annotations

DDL = (
    # ── Caja ─────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS central_cash_shifts (
        shift_id          UUID PRIMARY KEY,
        event_id          UUID NOT NULL UNIQUE REFERENCES sync_inbox (event_id),
        branch_id         UUID NOT NULL,
        station_id        UUID NOT NULL,
        register_id       UUID,
        cashier_user_id   UUID,
        opening_amount    NUMERIC NOT NULL,
        opened_at         TIMESTAMPTZ NOT NULL,
        status            TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
        closed_at         TIMESTAMPTZ,
        z_cut_id          UUID
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS central_cash_movements (
        movement_id     UUID PRIMARY KEY,
        event_id        UUID NOT NULL UNIQUE REFERENCES sync_inbox (event_id),
        branch_id       UUID NOT NULL,
        shift_id        UUID,
        movement_kind   TEXT NOT NULL,
        signed_amount   NUMERIC NOT NULL,
        reversal_of_id  UUID,
        sale_id         UUID,
        occurred_at     TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_cash_movements_shift ON central_cash_movements (shift_id)",
    """
    CREATE TABLE IF NOT EXISTS central_cash_cuts (
        cut_id           UUID PRIMARY KEY,
        event_id         UUID NOT NULL UNIQUE REFERENCES sync_inbox (event_id),
        branch_id        UUID NOT NULL,
        shift_id         UUID NOT NULL,
        document_number  TEXT NOT NULL,
        expected_cash    NUMERIC NOT NULL,
        counted_cash     NUMERIC NOT NULL,
        difference       NUMERIC NOT NULL,
        business_date    DATE,
        occurred_at      TIMESTAMPTZ NOT NULL
    )
    """,
    # ── Finanzas ─────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS central_journal_entries (
        entry_id              UUID PRIMARY KEY,
        event_id              UUID NOT NULL UNIQUE REFERENCES sync_inbox (event_id),
        branch_id             UUID NOT NULL,
        entry_number          TEXT NOT NULL,
        entry_date            DATE NOT NULL,
        posting_date          DATE NOT NULL,
        source_module         TEXT,
        source_document_ref   TEXT,
        posting_purpose       TEXT,
        currency_code         TEXT NOT NULL,
        base_currency_code    TEXT NOT NULL,
        total_debits          NUMERIC NOT NULL,
        total_credits         NUMERIC NOT NULL,
        reversal_of_entry_id  UUID,
        occurred_at           TIMESTAMPTZ NOT NULL,
        CHECK (total_debits = total_credits)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_journal_entries_branch"
    " ON central_journal_entries (branch_id, posting_date)",
    """
    CREATE TABLE IF NOT EXISTS central_journal_lines (
        entry_id        UUID NOT NULL REFERENCES central_journal_entries (entry_id),
        line_index      INTEGER NOT NULL CHECK (line_index >= 0),
        account_code    TEXT NOT NULL,
        account_type    TEXT,
        is_receivable   BOOLEAN NOT NULL DEFAULT false,
        debit           NUMERIC NOT NULL CHECK (debit >= 0),
        credit          NUMERIC NOT NULL CHECK (credit >= 0),
        line_role       TEXT,
        line_branch_id  UUID,
        cost_center_id  UUID,
        customer_id     UUID,
        supplier_id     UUID,
        product_id      UUID,
        PRIMARY KEY (entry_id, line_index)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_journal_lines_account ON central_journal_lines (account_code)",
    "CREATE INDEX IF NOT EXISTS ix_central_journal_lines_customer ON central_journal_lines (customer_id)"
    " WHERE is_receivable",
    """
    CREATE OR REPLACE VIEW central_trial_balance AS
    SELECT e.branch_id, l.account_code, l.account_type,
           SUM(l.debit) AS debits, SUM(l.credit) AS credits,
           SUM(l.debit) - SUM(l.credit) AS balance
    FROM central_journal_lines l
    JOIN central_journal_entries e ON e.entry_id = l.entry_id
    GROUP BY e.branch_id, l.account_code, l.account_type
    """,
    """
    CREATE OR REPLACE VIEW central_receivables AS
    SELECT l.customer_id, SUM(l.debit) - SUM(l.credit) AS balance,
           COUNT(DISTINCT e.branch_id) AS branches
    FROM central_journal_lines l
    JOIN central_journal_entries e ON e.entry_id = l.entry_id
    WHERE l.is_receivable AND l.customer_id IS NOT NULL
    GROUP BY l.customer_id
    """,
    # ── Crédito ──────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS central_credit_accounts (
        profile_id        UUID PRIMARY KEY,
        customer_id       UUID NOT NULL,
        branch_id         UUID NOT NULL,
        credit_limit      NUMERIC NOT NULL DEFAULT 0,
        status            TEXT NOT NULL,
        last_event_id     UUID NOT NULL REFERENCES sync_inbox (event_id),
        updated_at        TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_credit_accounts_customer"
    " ON central_credit_accounts (customer_id)",
    """
    CREATE OR REPLACE VIEW central_credit_exposure AS
    SELECT a.customer_id, MAX(a.credit_limit) AS credit_limit,
           COALESCE(MAX(r.balance), 0) AS receivable,
           MAX(a.credit_limit) - COALESCE(MAX(r.balance), 0) AS available,
           BOOL_OR(a.status = 'ACTIVE') AS active
    FROM central_credit_accounts a
    LEFT JOIN central_receivables r ON r.customer_id = a.customer_id
    GROUP BY a.customer_id
    """,
    # ── Fidelidad ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS central_loyalty_transactions (
        transaction_id         UUID PRIMARY KEY,
        first_event_id         UUID NOT NULL REFERENCES sync_inbox (event_id),
        last_event_id          UUID NOT NULL REFERENCES sync_inbox (event_id),
        loyalty_account_id     UUID NOT NULL,
        customer_id            UUID,
        membership_id          UUID,
        branch_id              UUID NOT NULL,
        transaction_type       TEXT NOT NULL,
        status                 TEXT NOT NULL,
        points_amount          NUMERIC NOT NULL,
        counts_toward_balance  BOOLEAN NOT NULL,
        sale_id                UUID,
        updated_at             TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_loyalty_customer ON central_loyalty_transactions (customer_id)",
    """
    CREATE OR REPLACE VIEW central_loyalty_balances AS
    SELECT customer_id,
           SUM(points_amount) FILTER (WHERE counts_toward_balance) AS points,
           COUNT(DISTINCT branch_id) AS branches
    FROM central_loyalty_transactions
    GROUP BY customer_id
    """,
)


def run(conn) -> None:
    with conn.cursor() as cur:
        for sentencia in DDL:
            cur.execute(sentencia)


up = run
