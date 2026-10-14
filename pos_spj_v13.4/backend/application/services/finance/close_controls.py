"""Controles de cierre — auxiliares contra mayor (auditoría d9f2bca F11/F16).

El cierre comprobaba sólo asientos desbalanceados y conciliaciones abiertas.
Un asiento equilibrado no garantiza que la deuda cuadre: una CxC creada sin
reconocimiento dejaba Clientes en −100 con el auxiliar en 0, y un CAPEX sin
pagar dejaba Proveedores en 100 sin CxP. Estos controles miden la diferencia
entre lo que dicen los auxiliares (CxC/CxP abiertas) y lo que dice el mayor en
sus cuentas de control, y la PERSISTEN como excepción del periodo. Una
excepción abierta bloquea el cierre hasta que desaparece (se vuelve a medir) o
alguien con permiso la autoriza con motivo.

La comparación es ESTRUCTURAL (saldo vigente del auxiliar contra saldo total
contabilizado de la cuenta de control): no depende de la fecha y no se
confunde con movimientos posteriores al periodo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork

CHECK_RECEIVABLES = "SUBLEDGER_RECEIVABLES"
CHECK_PAYABLES = "SUBLEDGER_PAYABLES"
CHECK_COMMERCIAL = "COMMERCIAL_INSTRUMENT"
CHECK_SALE_CREDIT = "SALE_CREDIT_VS_RECEIVABLE"


def _decimal_sum(values) -> Decimal:
    total = Decimal("0")
    for value in values:
        if value is not None and str(value).strip() != "":
            total += Decimal(str(value))
    return total


def _ledger_balance(uow: FinanceUnitOfWork, account_id: str, currency_code: str,
                    *, natural_debit: bool) -> Decimal:
    rows = uow.connection.execute(
        "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
        " JOIN journal_entries je ON je.id = jl.journal_entry_id"
        " WHERE jl.account_id = ? AND je.status IN ('POSTED','REVERSED')"
        " AND je.currency_code = ?", (account_id, currency_code)).fetchall()
    debits = _decimal_sum(r[0] for r in rows)
    credits = _decimal_sum(r[1] for r in rows)
    return debits - credits if natural_debit else credits - debits


class FinanceCloseControls:
    def __init__(self, materiality_threshold: str = "0.01") -> None:
        self._threshold = Decimal(materiality_threshold)

    def run(self, connection, *, period_code: str, as_of: date,
            currency_code: str = "MXN") -> list[dict]:
        """Mide, persiste (en su propia transacción) y devuelve las excepciones
        abiertas del periodo y anteriores."""
        with FinanceUnitOfWork(connection) as uow:
            self._subledger(uow, period_code, as_of, currency_code, CHECK_RECEIVABLES,
                            profile_key="SALE", role="receivable_account_id",
                            table="receivables",
                            open_statuses="('OPEN','PARTIALLY_COLLECTED')",
                            natural_debit=True)
            self._subledger(uow, period_code, as_of, currency_code, CHECK_PAYABLES,
                            profile_key="PURCHASE", role="payable_account_id",
                            table="payables",
                            open_statuses="('OPEN','SCHEDULED','PARTIALLY_PAID')",
                            natural_debit=False)
            return uow.close_exceptions.list_open(period_code)

    def _subledger(self, uow, period_code, as_of, currency_code, check_type, *,
                   profile_key, role, table, open_statuses, natural_debit) -> None:
        profile = uow.posting_profiles.find_effective(profile_key, as_of)
        if profile is None or not profile.has_account(role):
            return
        account_id = profile.account_for(role)
        subledger = _decimal_sum(r[0] for r in uow.connection.execute(
            f"SELECT outstanding_amount FROM {table} WHERE status IN {open_statuses}"
            " AND currency_code = ?", (currency_code,)).fetchall())
        ledger = _ledger_balance(uow, account_id, currency_code, natural_debit=natural_debit)
        difference = ledger - subledger
        subject = f"{profile_key}:{account_id}"
        if abs(difference) > self._threshold:
            uow.close_exceptions.open_or_refresh(
                period_code=period_code, check_type=check_type, subject=subject,
                expected=Money(subledger, currency_code).to_string(),
                actual=Money(ledger, currency_code).to_string(),
                difference=Money(difference, currency_code).to_string(),
                currency_code=currency_code)
            still = {subject}
        else:
            still = set()
        uow.close_exceptions.resolve_missing(period_code=period_code, check_type=check_type,
                                             still_open_subjects=still)
