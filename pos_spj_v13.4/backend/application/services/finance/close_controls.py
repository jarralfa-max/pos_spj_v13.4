"""Controles de cierre — auxiliares contra mayor (auditoría d9f2bca F11/F16).

Un asiento equilibrado no garantiza que la deuda cuadre: estos controles miden
la diferencia entre lo que dicen los auxiliares (CxC/CxP abiertas) y lo que
dice el mayor en sus cuentas de control, y la PERSISTEN como excepción del
periodo. Una excepción abierta bloquea el cierre hasta que desaparece (se
vuelve a medir) o alguien con permiso la autoriza con motivo.

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
                            subledger=uow.receivables, natural_debit=True)
            self._subledger(uow, period_code, as_of, currency_code, CHECK_PAYABLES,
                            profile_key="PURCHASE", role="payable_account_id",
                            subledger=uow.payables, natural_debit=False)
            return uow.close_exceptions.list_open(period_code)

    def _subledger(self, uow, period_code, as_of, currency_code, check_type, *,
                   profile_key, role, subledger, natural_debit) -> None:
        profile = uow.posting_profiles.find_effective(profile_key, as_of)
        if profile is None or not profile.has_account(role):
            return
        account_id = profile.account_for(role)
        auxiliary = subledger.open_outstanding_total(currency_code)
        ledger = uow.journal_entries.account_balance(account_id, currency_code,
                                                     natural_debit=natural_debit)
        difference = ledger - auxiliary
        subject = f"{profile_key}:{account_id}"
        if abs(difference) > self._threshold:
            uow.close_exceptions.open_or_refresh(
                period_code=period_code, check_type=check_type, subject=subject,
                expected=Money(auxiliary, currency_code).to_string(),
                actual=Money(ledger, currency_code).to_string(),
                difference=Money(difference, currency_code).to_string(),
                currency_code=currency_code)
            still = {subject}
        else:
            still = set()
        uow.close_exceptions.resolve_missing(period_code=period_code, check_type=check_type,
                                             still_open_subjects=still)
