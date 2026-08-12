"""CustomerAccountsReceivableSummaryQuery (§40): "CxC: Finanzas es dueño de
documentos/vencimientos/pagos/saldo/reversos; CRM solo muestra
exposición/saldo/vencido/próximo vencimiento... no crear ledger financiero
paralelo."

Reads Finanzas' own ``cuentas_por_cobrar`` table directly — read-only,
parameterized, never a CREATE TABLE/INSERT/UPDATE against it (enforced by
``tests/architecture/test_customers_crm_does_not_duplicate_cxc.py``, CRM-1).
This is the one sanctioned exception to "don't reach into another bounded
context's tables": a live summary read, not a second source of truth. Never
persisted anywhere in this bounded context — see
``CustomerCreditProfile``'s module docstring for why a cached
``current_exposure`` column would go stale.

``cuentas_por_cobrar`` has no due-date column — the due date is computed as
``fecha + payment_terms_days`` (from the caller's ``CustomerCreditProfile``),
same derived-not-stored discipline as CRM-6/7's OVERDUE/breach-status.

**Known data-model gap, not a bug in this query**: ``cuentas_por_cobrar.
cliente_id`` was created against the legacy integer ``clientes`` table
(``migrations/m000_base_schema.py``), not CRM-3's UUIDv7 ``customers``
table — the CRM-0 audit documented these as two unreconciled customer
identities, and unifying them is explicitly deferred to CRM-21/22. Until
then, this query correctly returns zero exposure for any customer that
only exists in the new ``customers`` table and has no matching legacy
``cliente_id`` rows — that is accurate given today's data, not a silent
failure to hide.

All amounts converted row-by-row to ``Decimal`` (REGLA CERO) — SQL
``SUM()`` over the underlying ``REAL`` columns is deliberately avoided to
keep summation precision-safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class CustomerAccountsReceivableSummary:
    customer_id: str
    current_exposure: Decimal
    overdue_amount: Decimal
    next_due_date: date | None
    open_documents_count: int


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


class CustomerAccountsReceivableSummaryQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def get_summary(
        self, customer_id: str, *, payment_terms_days: int = 0, as_of: date | None = None,
    ) -> CustomerAccountsReceivableSummary:
        as_of = as_of or date.today()
        rows = self._conn.execute(
            "SELECT saldo_pendiente, fecha, fecha_pago FROM cuentas_por_cobrar"
            " WHERE cliente_id=? AND estado NOT IN ('pagado', 'cancelada', 'cancelado')",
            (customer_id,)).fetchall()

        exposure = Decimal("0")
        overdue = Decimal("0")
        next_due: date | None = None
        count = 0
        for saldo_pendiente, fecha, fecha_pago in rows:
            if saldo_pendiente is None:
                continue
            amount = Decimal(str(saldo_pendiente))
            if amount <= 0:
                continue
            count += 1
            exposure += amount
            if fecha_pago:
                continue  # already paid — never overdue, never "next due"
            billed_on = _parse_date(fecha)
            if billed_on is None:
                continue
            due_date = billed_on + timedelta(days=payment_terms_days)
            if due_date < as_of:
                overdue += amount
            elif next_due is None or due_date < next_due:
                next_due = due_date

        return CustomerAccountsReceivableSummary(
            customer_id=customer_id, current_exposure=exposure, overdue_amount=overdue,
            next_due_date=next_due, open_documents_count=count)
