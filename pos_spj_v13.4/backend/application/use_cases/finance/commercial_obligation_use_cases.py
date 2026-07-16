"""Commercial obligation use cases — administrative routes.

Manual corrections require: permission (checked by the caller layer against
``finance.commercial_adjustment.*``), reason, acting user and operation id —
and always resolve into a posted entry or reversal, never an edit.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.commercial_instrument_processor import (
    CommercialInstrumentProcessor,
)
from backend.domain.finance.entities.commercial_obligation import CommercialObligation
from backend.domain.finance.enums import CommercialInstrumentType
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class RecognizeCommercialObligationUseCase:
    def __init__(self) -> None:
        self._processor = CommercialInstrumentProcessor()

    def execute(self, connection, *, instrument_type: CommercialInstrumentType,
                source_module: str, source_instrument_id: str, amount: str,
                on_date: date, currency_code: str = "MXN",
                customer_id: str | None = None, branch_id: str | None = None,
                program_id: str | None = None, funding_party: str | None = None,
                expires_at: str | None = None, operation_id: str) -> CommercialObligation:
        with FinanceUnitOfWork(connection) as uow:
            return self._processor.recognize(
                uow, instrument_type=instrument_type, source_module=source_module,
                source_instrument_id=source_instrument_id,
                amount=Money.from_string(amount, currency_code),
                on_date=on_date, operation_id=operation_id,
                customer_id=customer_id, branch_id=branch_id,
                program_id=program_id, funding_party=funding_party,
                expires_at=expires_at,
            )


class SettleCommercialObligationUseCase:
    def __init__(self) -> None:
        self._processor = CommercialInstrumentProcessor()

    def execute(self, connection, *, instrument_type: CommercialInstrumentType,
                source_instrument_id: str, amount: str, on_date: date,
                currency_code: str = "MXN", redemption_id: str | None = None,
                actual_cost: str | None = None, operation_id: str) -> CommercialObligation:
        with FinanceUnitOfWork(connection) as uow:
            return self._processor.redeem(
                uow, instrument_type=instrument_type,
                source_instrument_id=source_instrument_id,
                amount=Money.from_string(amount, currency_code),
                on_date=on_date, operation_id=operation_id,
                redemption_id=redemption_id,
                actual_cost=(Money.from_string(actual_cost, currency_code)
                             if actual_cost else None),
            )


class ReleaseExpiredCommercialObligationUseCase:
    def __init__(self) -> None:
        self._processor = CommercialInstrumentProcessor()

    def execute(self, connection, *, instrument_type: CommercialInstrumentType,
                source_instrument_id: str, on_date: date,
                operation_id: str) -> CommercialObligation:
        with FinanceUnitOfWork(connection) as uow:
            return self._processor.expire(
                uow, instrument_type=instrument_type,
                source_instrument_id=source_instrument_id,
                on_date=on_date, operation_id=operation_id,
            )


class ReverseCommercialObligationUseCase:
    """Manual reversal: requires reason and acting user (audited)."""

    def __init__(self) -> None:
        self._processor = CommercialInstrumentProcessor()

    def execute(self, connection, *, instrument_type: CommercialInstrumentType,
                source_instrument_id: str, on_date: date, reason: str,
                actor_id: str, operation_id: str) -> CommercialObligation:
        if not reason or not reason.strip():
            raise FinanceDomainError("El reverso manual requiere un motivo")
        if not actor_id:
            raise FinanceDomainError("El reverso manual requiere el usuario que lo ejecuta")
        with FinanceUnitOfWork(connection) as uow:
            return self._processor.reverse(
                uow, instrument_type=instrument_type,
                source_instrument_id=source_instrument_id,
                on_date=on_date, operation_id=operation_id,
                reason=f"{reason.strip()} (por {actor_id})",
            )
