"""Real ``TransferRequestNumberGenerator`` (TRF-2026-000001 style).

``StaticTransferRequestNumberGenerator`` in
``backend/application/transfers/use_cases/transfer_request_use_cases.py`` always
returns the same value — a test stub, unusable in production since
``stock_transfers.transfer_number`` is ``UNIQUE``. This counts existing numbers
for the current year and formats the next one.
"""
from __future__ import annotations

from datetime import datetime, timezone


class SqlTransferRequestNumberGenerator:
    def __init__(self, connection) -> None:
        self._db = connection

    def next_transfer_number(self) -> str:
        year = datetime.now(timezone.utc).year
        prefix = f"TRF-{year}-"
        row = self._db.execute(
            "SELECT COUNT(*) FROM stock_transfers WHERE transfer_number LIKE ?",
            (f"{prefix}%",)).fetchone()
        count = row[0] if row is not None else 0
        return f"{prefix}{count + 1:06d}"
