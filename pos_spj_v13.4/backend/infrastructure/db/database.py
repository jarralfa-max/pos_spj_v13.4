"""Database connection configuration skeleton.

This module intentionally avoids schema creation. Schema changes belong only in
`migrations/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Protocol

from backend.infrastructure.db.dialect import DatabaseDialect
from backend.shared.app_paths import AppPaths


class ConnectionFactory(Protocol):
    def __call__(self) -> Any:
        """Return a DB-API compatible connection."""


@dataclass(frozen=True)
class DatabaseSettings:
    dialect: DatabaseDialect
    database_url: str

    @classmethod
    def sqlite(cls, paths: AppPaths, filename: str = "spj.sqlite3") -> "DatabaseSettings":
        return cls(
            dialect=DatabaseDialect.SQLITE,
            database_url=f"sqlite:///{paths.sqlite_database_path(filename)}",
        )


def create_connection_factory(settings: DatabaseSettings) -> ConnectionFactory:
    if settings.dialect is DatabaseDialect.SQLITE:
        database_path = _sqlite_path_from_url(settings.database_url)

        def connect_sqlite() -> sqlite3.Connection:
            database_path.parent.mkdir(parents=True, exist_ok=True)
            return sqlite3.connect(database_path)

        return connect_sqlite

    if settings.dialect is DatabaseDialect.POSTGRESQL:
        def connect_postgresql() -> Any:
            raise NotImplementedError(
                "PostgreSQL connection factory is reserved for the future API/backend migration."
            )

        return connect_postgresql

    raise ValueError(f"Unsupported database dialect: {settings.dialect}")


def _sqlite_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Invalid SQLite database URL: {database_url}")
    return Path(database_url[len(prefix):]).expanduser()
