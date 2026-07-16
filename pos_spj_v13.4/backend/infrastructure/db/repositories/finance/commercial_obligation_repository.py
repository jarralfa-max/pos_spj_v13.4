"""CommercialObligation repository."""

from __future__ import annotations

from backend.domain.finance.entities.commercial_obligation import CommercialObligation
from backend.domain.finance.enums import (
    CommercialInstrumentType,
    CommercialObligationStatus,
    RecognitionBasis,
)
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, instrument_type, source_module, source_instrument_id, recognition_basis,"
            " customer_id, branch_id, currency_code, original_amount, recognized_amount,"
            " redeemed_amount, released_amount, status, issued_at, expires_at,"
            " operation_id, created_at, updated_at")


def _to_entity(row: dict) -> CommercialObligation:
    currency = row["currency_code"]
    return CommercialObligation(
        id=row["id"],
        instrument_type=CommercialInstrumentType(row["instrument_type"]),
        source_module=row["source_module"],
        source_instrument_id=row["source_instrument_id"],
        recognition_basis=RecognitionBasis(row["recognition_basis"]),
        original_amount=Money.from_string(row["original_amount"], currency),
        recognized_amount=Money.from_string(row["recognized_amount"], currency),
        redeemed_amount=Money.from_string(row["redeemed_amount"], currency),
        released_amount=Money.from_string(row["released_amount"], currency),
        operation_id=row["operation_id"],
        customer_id=row["customer_id"], branch_id=row["branch_id"],
        status=CommercialObligationStatus(row["status"]),
        issued_at=row["issued_at"], expires_at=row["expires_at"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class CommercialObligationRepository(FinanceRepositoryBase):
    def save(self, obligation: CommercialObligation) -> None:
        self._execute(
            f"INSERT INTO commercial_obligations ({_COLUMNS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (obligation.id, obligation.instrument_type.value, obligation.source_module,
             obligation.source_instrument_id, obligation.recognition_basis.value,
             obligation.customer_id, obligation.branch_id,
             obligation.original_amount.currency_code,
             obligation.original_amount.to_string(), obligation.recognized_amount.to_string(),
             obligation.redeemed_amount.to_string(), obligation.released_amount.to_string(),
             obligation.status.value, obligation.issued_at, obligation.expires_at,
             obligation.operation_id, obligation.created_at, obligation.updated_at),
        )

    def update(self, obligation: CommercialObligation) -> None:
        self._execute(
            "UPDATE commercial_obligations SET recognized_amount=?, redeemed_amount=?,"
            " released_amount=?, status=?, expires_at=?, updated_at=? WHERE id=?",
            (obligation.recognized_amount.to_string(), obligation.redeemed_amount.to_string(),
             obligation.released_amount.to_string(), obligation.status.value,
             obligation.expires_at, obligation.updated_at, obligation.id),
        )

    def get(self, obligation_id: str) -> CommercialObligation | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM commercial_obligations WHERE id=?", (obligation_id,)
        )
        return _to_entity(row) if row else None

    def find_by_instrument(
        self, instrument_type: CommercialInstrumentType, source_instrument_id: str,
    ) -> CommercialObligation | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM commercial_obligations"
            " WHERE instrument_type=? AND source_instrument_id=?",
            (instrument_type.value, source_instrument_id),
        )
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> CommercialObligation | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM commercial_obligations WHERE operation_id=?",
            (operation_id,),
        )
        return _to_entity(row) if row else None

    def list_open(self, instrument_type: CommercialInstrumentType | None = None) -> list[CommercialObligation]:
        if instrument_type is None:
            rows = self._query(
                f"SELECT {_COLUMNS} FROM commercial_obligations"
                " WHERE status IN ('OPEN','PARTIALLY_REDEEMED')"
            )
        else:
            rows = self._query(
                f"SELECT {_COLUMNS} FROM commercial_obligations"
                " WHERE status IN ('OPEN','PARTIALLY_REDEEMED') AND instrument_type=?",
                (instrument_type.value,),
            )
        return [_to_entity(row) for row in rows]
