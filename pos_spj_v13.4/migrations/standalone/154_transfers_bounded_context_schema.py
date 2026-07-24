"""TRF-3: create the born-clean canonical Transfers schema.

No legacy table is copied or bridged. TRF-22 completed the zero-consumer cutover,
so this is the only Transfers schema installed by a clean bootstrap.
"""
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema


def run(connection) -> None:
    create_transfers_schema(connection)
    connection.commit()


up = run
