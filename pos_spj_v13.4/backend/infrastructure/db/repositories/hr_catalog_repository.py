"""SQLite repositories for configurable HR catalogs."""

from __future__ import annotations

from sqlite3 import Connection

from backend.domain.hr.entities import ContractTypeCatalogItem, PaymentFrequencyCatalogItem


class SQLiteContractTypeRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save(self, contract_type: ContractTypeCatalogItem) -> None:
        self._connection.execute(
            """
            INSERT INTO contract_types (id, code, name, active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                code = excluded.code,
                name = excluded.name,
                active = excluded.active
            """,
            (contract_type.id, contract_type.code, contract_type.name, 1 if contract_type.active else 0),
        )


class SQLitePaymentFrequencyRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save(self, payment_frequency: PaymentFrequencyCatalogItem) -> None:
        self._connection.execute(
            """
            INSERT INTO payment_frequencies (id, code, name, active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                code = excluded.code,
                name = excluded.name,
                active = excluded.active
            """,
            (payment_frequency.id, payment_frequency.code, payment_frequency.name, 1 if payment_frequency.active else 0),
        )
