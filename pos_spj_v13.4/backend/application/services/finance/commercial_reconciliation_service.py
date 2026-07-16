"""Commercial instrument reconciliation — operational balance vs ledger.

Compares, per instrument type:
- the operational outstanding balance reported by the owning module;
- the open obligations recognized by Finance;
- redemptions, expirations and reversals already posted.

Material unexplained differences emit
COMMERCIAL_RECONCILIATION_DIFFERENCE_DETECTED and block the monthly close.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from backend.domain.finance.enums import CommercialInstrumentType
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


@dataclass(frozen=True, slots=True)
class InstrumentReconciliationRow:
    instrument_type: str
    operational_balance: str
    financial_outstanding: str
    difference: str
    open_obligations: int
    is_material: bool


class CommercialReconciliationService:
    def __init__(self, materiality_threshold: str = "0.01") -> None:
        self._threshold = materiality_threshold

    def reconcile(
        self,
        connection,
        operational_balances: dict[str, str],
        *,
        currency_code: str = "MXN",
        operation_id: str | None = None,
    ) -> list[InstrumentReconciliationRow]:
        """``operational_balances``: {instrument_type: decimal-string outstanding}
        reported by the owning modules (loyalty, promotions, …)."""
        threshold = Money.from_string(self._threshold, currency_code)
        rows: list[InstrumentReconciliationRow] = []
        with FinanceUnitOfWork(connection) as uow:
            for type_name, reported in operational_balances.items():
                instrument_type = CommercialInstrumentType(type_name)
                operational = Money.from_string(str(reported), currency_code)
                open_obligations = uow.commercial_obligations.list_open(instrument_type)
                outstanding = Money.zero(currency_code)
                for obligation in open_obligations:
                    outstanding = outstanding.add(obligation.outstanding_amount)
                difference = operational.subtract(outstanding)
                is_material = difference.abs() > threshold
                rows.append(InstrumentReconciliationRow(
                    instrument_type=instrument_type.value,
                    operational_balance=operational.to_string(),
                    financial_outstanding=outstanding.to_string(),
                    difference=difference.to_string(),
                    open_obligations=len(open_obligations),
                    is_material=is_material,
                ))
                if is_material:
                    uow.outbox.enqueue(
                        event_id=new_uuid(),
                        event_name=(EventName
                                    .COMMERCIAL_RECONCILIATION_DIFFERENCE_DETECTED.value),
                        payload_json=json.dumps({
                            "instrument_type": instrument_type.value,
                            "operational_balance": operational.to_string(),
                            "financial_outstanding": outstanding.to_string(),
                            "difference": difference.to_string(),
                            "currency_code": currency_code,
                        }),
                        operation_id=operation_id or new_uuid(),
                    )
        return rows

    @staticmethod
    def unposted_events_report(connection) -> list[dict]:
        """Events received but without any posted entry (integration exceptions)."""
        with FinanceUnitOfWork(connection) as uow:
            return uow.processed_events.list_without_journal_entry()
