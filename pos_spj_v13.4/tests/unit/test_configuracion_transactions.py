"""FASE 3 — UnitOfWork / transaction boundary tests for CONFIGURACION.

Protects the canonical transaction contract:
- the repository never commits/rolls back,
- the application service (use case) commits exactly once via the UnitOfWork,
- domain events are published only AFTER a successful commit,
- when the commit fails, no event is published.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.shared.ids import new_uuid
from core.services.configuration_settings_service import (
    PermissionEventPublisher,
    RoleManagementService,
)
from repositories.config_repository import ConfigRepository

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


class _SpyConnection:
    """Wraps a real connection, counting/intercepting commit and rollback."""

    def __init__(self, real, log=None, fail_commit=False):
        self._real = real
        self.commit_count = 0
        self.rollback_count = 0
        self._log = log if log is not None else []
        self._fail_commit = fail_commit

    def __getattr__(self, name):  # delegate execute/executescript/row_factory/...
        return getattr(self._real, name)

    def commit(self):
        self.commit_count += 1
        self._log.append("commit")
        if self._fail_commit:
            raise sqlite3.OperationalError("commit failed")
        return self._real.commit()

    def rollback(self):
        self.rollback_count += 1
        self._log.append("rollback")
        return self._real.rollback()


class _RecordingPublisher(PermissionEventPublisher):
    def __init__(self, log):
        super().__init__()
        self._log = log

    def publish(self, *args, **kwargs):
        self._log.append("publish")
        return super().publish(*args, **kwargs)


def _spy(log=None, fail_commit=False) -> _SpyConnection:
    real = sqlite3.connect(":memory:")
    real.row_factory = sqlite3.Row
    real.execute(
        "CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, "
        "nombre TEXT UNIQUE, descripcion TEXT)"
    )
    real.commit()
    return _SpyConnection(real, log=log, fail_commit=fail_commit)


def test_configuracion_repository_has_no_commit() -> None:
    content = (PACKAGE_ROOT / "repositories" / "config_repository.py").read_text(encoding="utf-8")
    assert ".commit(" not in content
    assert ".rollback(" not in content
    assert "def _commit" not in content


def test_configuracion_usecase_commits_once() -> None:
    spy = _spy()
    service = RoleManagementService(ConfigRepository(spy), _RecordingPublisher([]))

    service.save_role(
        role_id=None, name="gerente", description="Gerente",
        operation_id=new_uuid(), actor="admin",
    )

    assert spy.commit_count == 1


def test_configuracion_event_published_after_commit() -> None:
    log: list[str] = []
    spy = _spy(log=log)
    service = RoleManagementService(ConfigRepository(spy), _RecordingPublisher(log))

    service.save_role(
        role_id=None, name="gerente", description="Gerente",
        operation_id=new_uuid(), actor="admin",
    )

    assert log == ["commit", "publish"]


def test_configuracion_no_event_when_commit_fails() -> None:
    spy = _spy(fail_commit=True)
    publisher = _RecordingPublisher([])
    service = RoleManagementService(ConfigRepository(spy), publisher)

    with pytest.raises(sqlite3.OperationalError):
        service.save_role(
            role_id=None, name="gerente", description="Gerente",
            operation_id=new_uuid(), actor="admin",
        )

    assert publisher.published_events == []
    assert spy.rollback_count == 1
