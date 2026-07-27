"""Database dialect metadata for SQLite now and PostgreSQL future support."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DatabaseDialect(str, Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"

    @classmethod
    def from_url(cls, database_url: str) -> "DatabaseDialect":
        normalized = database_url.lower()
        if normalized.startswith(("sqlite://", "sqlite:///")):
            return cls.SQLITE
        if normalized.startswith(("postgresql://", "postgres://")):
            return cls.POSTGRESQL
        raise ValueError(f"Unsupported database URL dialect: {database_url}")


@dataclass(frozen=True)
class DialectCapabilities:
    dialect: DatabaseDialect
    paramstyle: str
    supports_returning: bool
    supports_native_upsert: bool


def get_dialect_capabilities(dialect: DatabaseDialect) -> DialectCapabilities:
    if dialect is DatabaseDialect.SQLITE:
        return DialectCapabilities(
            dialect=dialect,
            paramstyle="qmark",
            supports_returning=True,
            supports_native_upsert=True,
        )

    if dialect is DatabaseDialect.POSTGRESQL:
        return DialectCapabilities(
            dialect=dialect,
            paramstyle="pyformat",
            supports_returning=True,
            supports_native_upsert=True,
        )

    raise ValueError(f"Unsupported database dialect: {dialect}")
