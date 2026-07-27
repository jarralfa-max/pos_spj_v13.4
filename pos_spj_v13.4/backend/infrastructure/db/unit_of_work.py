"""Base Unit of Work abstraction for future application services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.infrastructure.db.database import ConnectionFactory
from backend.infrastructure.db.transaction import Transaction


class UnitOfWork(ABC):
    """Abstract transaction boundary for application use cases."""

    connection: Any

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError


class DbApiUnitOfWork(UnitOfWork):
    """DB-API UnitOfWork skeleton shared by desktop and future API entrypoints."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory
        self.connection: Any | None = None
        self._transaction: Transaction | None = None

    def __enter__(self) -> "DbApiUnitOfWork":
        self.connection = self._connection_factory()
        self._transaction = Transaction(self.connection)
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: object) -> None:
        if self._transaction is None:
            return
        self._transaction.__exit__(exc_type, exc, traceback)
        self._transaction = None
        self.connection = None

    def commit(self) -> None:
        if self._transaction is None:
            raise RuntimeError("UnitOfWork is not active")
        self._transaction.commit()

    def rollback(self) -> None:
        if self._transaction is None:
            raise RuntimeError("UnitOfWork is not active")
        self._transaction.rollback()


class ConnectionUnitOfWork(UnitOfWork):
    """UnitOfWork over an existing shared connection (desktop application services).

    Owns the transaction boundary without recreating or closing the long-lived
    desktop connection. Commits on success, rolls back on error. Safe under
    SQLite autocommit (``isolation_level=None``), where ``commit()`` is a
    harmless no-op. Repositories must not commit/rollback; the owning
    application service / use case drives this boundary instead.
    """

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self._completed = False

    def __enter__(self) -> "ConnectionUnitOfWork":
        self._completed = False
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: object) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._completed:
            self.commit()
        return False

    def commit(self) -> None:
        self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        rollback = getattr(self.connection, "rollback", None)
        if rollback is not None:
            try:
                rollback()
            except Exception:
                pass
        self._completed = True
