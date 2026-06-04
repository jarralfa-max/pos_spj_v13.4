"""Transaction boundary helpers for application services and use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Transaction:
    """Small DB-API transaction wrapper.

    UI code must not use this directly. Use cases should receive a UnitOfWork
    abstraction that owns this transaction boundary.
    """

    connection: Any
    _completed: bool = False

    def commit(self) -> None:
        self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        self.connection.rollback()
        self._completed = True

    def close(self) -> None:
        close = getattr(self.connection, "close", None)
        if close is not None:
            close()

    def __enter__(self) -> "Transaction":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: object) -> None:
        if exc_type is None and not self._completed:
            self.commit()
        elif exc_type is not None and not self._completed:
            self.rollback()
        self.close()
