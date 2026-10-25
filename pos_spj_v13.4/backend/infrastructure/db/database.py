"""Database connection configuration skeleton.

This module intentionally avoids schema creation. Schema changes belong only in
`migrations/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit, urlunsplit

from backend.infrastructure.db.dialect import DatabaseDialect
from backend.shared.app_paths import AppPaths


class ConnectionFactory(Protocol):
    def __call__(self) -> Any:
        """Return a DB-API compatible connection."""


#: Variable de entorno con la cadena de conexión del PostgreSQL central. El
#: secreto vive en el servidor (systemd `EnvironmentFile`, fuera del repo) y
#: NUNCA en el cliente Windows: las estaciones hablan con la API, no con la base.
POSTGRES_DSN_ENV = "SPJ_PG_DSN"


class PostgresConfigurationError(RuntimeError):
    """Falta o es inválida la configuración del PostgreSQL central."""


@dataclass(frozen=True)
class DatabaseSettings:
    dialect: DatabaseDialect
    database_url: str = field(repr=False)
    #: Límites del servidor central (segundos / milisegundos).
    connect_timeout_s: int = 10
    statement_timeout_ms: int = 30_000
    application_name: str = "spj-central"

    def __repr__(self) -> str:   # nunca imprimir la contraseña en logs
        return (f"DatabaseSettings(dialect={self.dialect.value!r}, "
                f"database_url={redact_url(self.database_url)!r})")

    @classmethod
    def postgresql(cls, database_url: str, **limits: Any) -> "DatabaseSettings":
        if DatabaseDialect.from_url(database_url) is not DatabaseDialect.POSTGRESQL:
            raise PostgresConfigurationError("La URL no es de PostgreSQL")
        return cls(dialect=DatabaseDialect.POSTGRESQL, database_url=database_url, **limits)

    @classmethod
    def postgresql_from_env(cls, environ: Mapping[str, str] | None = None,
                            **limits: Any) -> "DatabaseSettings":
        valor = (environ if environ is not None else os.environ).get(POSTGRES_DSN_ENV, "")
        if not valor.strip():
            raise PostgresConfigurationError(
                f"Falta {POSTGRES_DSN_ENV}: la cadena de conexión del PostgreSQL central "
                "se configura en el servidor, fuera del repositorio.")
        return cls.postgresql(valor.strip(), **limits)

    @classmethod
    def sqlite(cls, paths: AppPaths) -> "DatabaseSettings":
        """The SAME database file the desktop uses (`AppPaths.database_path`).

        Until 2026-10-14 this pointed at `<data>/db/spj.sqlite3`, a file no
        other component ever wrote: an API built on it would have answered
        from an empty database.
        """
        return cls(
            dialect=DatabaseDialect.SQLITE,
            database_url=f"sqlite:///{paths.database_path}",
        )


def create_connection_factory(settings: DatabaseSettings, *,
                              check_same_thread: bool = True) -> ConnectionFactory:
    """`check_same_thread=False` sólo para un proceso que serializa el acceso a
    una conexión compartida entre hilos (el host de la API de Logística)."""
    if settings.dialect is DatabaseDialect.SQLITE:
        database_path = _sqlite_path_from_url(settings.database_url)

        def connect_sqlite() -> sqlite3.Connection:
            database_path.parent.mkdir(parents=True, exist_ok=True)
            return sqlite3.connect(database_path, check_same_thread=check_same_thread)

        return connect_sqlite

    if settings.dialect is DatabaseDialect.POSTGRESQL:
        return _postgresql_factory(settings)

    raise ValueError(f"Unsupported database dialect: {settings.dialect}")


def _postgresql_factory(settings: DatabaseSettings) -> ConnectionFactory:
    """Conexiones psycopg 3 al PostgreSQL central (arquitectura híbrida, Slice 3).

    Sólo el servidor central la usa (API de sincronización, consultas
    corporativas). Transacción explícita (`autocommit=False`), tiempo límite de
    conexión y de sentencia, y nombre de aplicación para ver en `pg_stat_activity`
    quién es quién. psycopg se importa al conectar: el escritorio no lo necesita.
    """
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise PostgresConfigurationError(
            "Falta el controlador psycopg 3 en el servidor central "
            "(requirements-server.txt).") from exc

    def connect_postgresql() -> Any:
        return psycopg.connect(
            settings.database_url, autocommit=False,
            connect_timeout=settings.connect_timeout_s,
            application_name=settings.application_name,
            options=f"-c statement_timeout={int(settings.statement_timeout_ms)}")

    return connect_postgresql


def redact_url(database_url: str) -> str:
    """La URL sin contraseña, para logs y mensajes."""
    try:
        partes = urlsplit(database_url)
    except ValueError:
        return "<url inválida>"
    if partes.password is None:
        return database_url
    servidor = partes.hostname or ""
    if partes.port:
        servidor = f"{servidor}:{partes.port}"
    usuario = f"{partes.username}:***@" if partes.username else "***@"
    return urlunsplit((partes.scheme, usuario + servidor, partes.path, partes.query,
                       partes.fragment))


def _sqlite_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Invalid SQLite database URL: {database_url}")
    return Path(database_url[len(prefix):]).expanduser()
