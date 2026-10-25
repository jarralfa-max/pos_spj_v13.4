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

Vencimiento (auditoría CRM F23, 2026-10-09): en ``receivables`` manda el
``due_date`` PACTADO del documento (lo fija el cobro a crédito con el plazo
del perfil en ese momento; si el plazo cambia después, los documentos viejos
conservan el suyo). Sólo la deuda histórica de ``cuentas_por_cobrar``, que no
tiene columna de vencimiento, y un documento sin ``due_date`` usan el respaldo
``fecha + payment_terms_days`` del perfil actual.

**Data-model note, not a bug in this query**: ``cuentas_por_cobrar.
cliente_id`` was created against the legacy ``clientes`` table
(``migrations/m000_base_schema.py`` — ``clientes.id`` is itself a TEXT
UUIDv7, just a separately-minted one, not an integer), not CRM-3's
``customers`` table. CRM-0 documented these as two unreconciled customer
identities; CRM-21 added a bridge column (``customers.legacy_customer_id``,
migration 193, resolved via ``ResolveLegacyCustomerUseCase``) but this
query itself needs no change from it — call it directly with the LEGACY
``cliente_id`` (not the new ``customers.id``) and it already returns real
exposure, since ``cuentas_por_cobrar`` was never migrated and still keys on
the legacy id.

Auditoría CRM F02 (2026-10-09): eso último era el defecto — la elegibilidad y la
ficha llaman con el id CANÓNICO, así que la deuda histórica de un cliente
migrado daba 0 y se le autorizaba crédito que no tenía. Ahora la consulta recibe
el id canónico y resuelve ella misma el puente (``customers.legacy_customer_id``):
busca la deuda histórica por ambos ids. Sin doble conteo: son tablas distintas y
ninguna venta se apuntó en las dos.

All amounts converted row-by-row to ``Decimal`` (REGLA CERO) — SQL
``SUM()`` over the underlying ``REAL`` columns is deliberately avoided to
keep summation precision-safe.

CRM-13 (§49): "CRM muestra saldo/vencido/exposición/estatus" — the fourth
item, ``receivable_status``, was the one field this query didn't expose
yet. Derived, never persisted (same discipline as the due-date computation
above and CRM-6/7's OVERDUE/breach-status): ``SIN_MOVIMIENTOS`` (no open
documents), ``VENCIDO`` (any open document past due), or ``AL_CORRIENTE``
(open documents, none overdue).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from backend.domain.finance.enums import OPEN_RECEIVABLE_STATUSES, sql_in

#: Estados con saldo exigible que publica Finanzas (FIN-ERP): una CxC vencida o en
#: disputa sigue consumiendo el límite de crédito.
_OPEN_RECEIVABLES = sql_in(OPEN_RECEIVABLE_STATUSES)


@dataclass(frozen=True)
class CustomerAccountsReceivableSummary:
    customer_id: str
    current_exposure: Decimal
    overdue_amount: Decimal
    next_due_date: date | None
    open_documents_count: int
    receivable_status: str


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

    def _table_exists(self, name: str) -> bool:
        return bool(self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
            (name,)).fetchone())

    def _legacy_rows(self, customer_id: str) -> list[tuple]:
        """Deuda histórica en `cuentas_por_cobrar`.

        Ya NADIE escribe esta tabla —su único escritor era el
        `CustomerCreditService` legacy, eliminado—, pero una instalación en
        marcha conserva ahí saldos reales que siguen debiéndose. Dejar de
        leerla pondría a esos clientes a cero de exposición y les abriría
        crédito que no tienen.
        """
        if not self._table_exists("cuentas_por_cobrar"):
            return []
        ids = self._identities(customer_id)
        marks = ",".join("?" for _ in ids)
        return [(row[0], row[1], row[2], None) for row in self._conn.execute(
            "SELECT saldo_pendiente, fecha, fecha_pago FROM cuentas_por_cobrar"
            f" WHERE cliente_id IN ({marks})"
            " AND estado NOT IN ('pagado', 'cancelada', 'cancelado')",
            ids).fetchall()]

    def _identities(self, customer_id: str) -> tuple[str, ...]:
        """El id canónico, su histórico y los de clientes fusionados en él (F02/F06)."""
        from backend.application.customers.identity import CustomerIdentityResolver
        return CustomerIdentityResolver(self._conn).all_ids(customer_id)

    def _canonical_rows(self, customer_id: str) -> list[tuple]:
        """Deuda viva en `receivables`, el modelo canónico de Finanzas.

        Es donde `CreateReceivableUseCase` apunta hoy toda venta a crédito. Sin
        esta mitad, el límite de crédito no se aplicaría en absoluto: la
        exposición daría cero por más que el cliente acumulara ventas a crédito.

        Se traduce a la misma forma `(saldo, fecha, fecha_pago)` que la legacy
        para que el cálculo de abajo sea uno solo. `fecha_pago` va a `None`
        siempre: un cobro parcial ya baja `outstanding_amount`, y una cuenta
        liquidada queda fuera por su estado, así que no hay nada que marcar
        como pagado sin dejar de deberse.

        No hay doble conteo: son tablas distintas y ninguna venta se apunta en
        las dos — la legacy dejó de recibir escrituras antes de que la canónica
        empezara.
        """
        if not self._table_exists("receivables"):
            return []
        # Auditoría CRM F06: la deuda de un cliente fusionado sigue contando para
        # el superviviente (los documentos contables no se reescriben).
        from backend.application.customers.identity import CustomerIdentityResolver
        ids = CustomerIdentityResolver(self._conn).canonical_ids(customer_id)
        marks = ",".join("?" for _ in ids)
        return [
            (row[0], row[1], None, row[2])
            for row in self._conn.execute(
                "SELECT outstanding_amount, issue_date, due_date FROM receivables"
                f" WHERE customer_id IN ({marks}) AND status IN {_OPEN_RECEIVABLES}",
                ids).fetchall()
        ]

    def get_summary(
        self, customer_id: str, *, payment_terms_days: int = 0, as_of: date | None = None,
    ) -> CustomerAccountsReceivableSummary:
        as_of = as_of or date.today()
        rows = [*self._legacy_rows(customer_id), *self._canonical_rows(customer_id)]

        exposure = Decimal("0")
        overdue = Decimal("0")
        next_due: date | None = None
        count = 0
        for saldo_pendiente, fecha, fecha_pago, pactado in rows:
            if saldo_pendiente is None:
                continue
            amount = Decimal(str(saldo_pendiente))
            if amount <= 0:
                continue
            count += 1
            exposure += amount
            if fecha_pago:
                continue  # already paid — never overdue, never "next due"
            due_date = _parse_date(pactado) if pactado else None
            if due_date is None:
                billed_on = _parse_date(fecha)
                if billed_on is None:
                    continue
                due_date = billed_on + timedelta(days=payment_terms_days)
            if due_date < as_of:
                overdue += amount
            elif next_due is None or due_date < next_due:
                next_due = due_date

        if count == 0:
            status = "SIN_MOVIMIENTOS"
        elif overdue > 0:
            status = "VENCIDO"
        else:
            status = "AL_CORRIENTE"

        return CustomerAccountsReceivableSummary(
            customer_id=customer_id, current_exposure=exposure, overdue_amount=overdue,
            next_due_date=next_due, open_documents_count=count, receivable_status=status)
