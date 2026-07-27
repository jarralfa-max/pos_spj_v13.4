"""FastAPI dependency providers for future API routes."""

from __future__ import annotations

from backend.infrastructure.db.database import DatabaseSettings, create_connection_factory
from backend.infrastructure.db.unit_of_work import DbApiUnitOfWork
from backend.shared.app_paths import AppPaths


def get_app_paths() -> AppPaths:
    return AppPaths.from_environment().ensure_directories()


def get_unit_of_work() -> DbApiUnitOfWork:
    paths = get_app_paths()
    settings = DatabaseSettings.sqlite(paths)
    return DbApiUnitOfWork(create_connection_factory(settings))
