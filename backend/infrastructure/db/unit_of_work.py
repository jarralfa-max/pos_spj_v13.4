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
