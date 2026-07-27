"""FASE 7 — event contract + operation_id idempotency for CONFIGURACION."""

from __future__ import annotations

import sqlite3
from uuid import UUID

import pytest

from backend.shared.ids import new_uuid
from core.services.configuration_settings_service import (
    ModuleAccessService,
    PermissionEventPublisher,
)
from repositories.config_repository import ConfigRepository

REQUIRED_EVENT_FIELDS = (
    "event_id", "event_name", "operation_id", "entity_id", "branch_id",
    "source_module", "occurred_at", "schema_version", "payload",
)
UUID_FIELDS = ("event_id", "operation_id", "entity_id", "branch_id")


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT UNIQUE, descripcion TEXT);
        CREATE TABLE rol_permisos(rol_id INTEGER, rol_uuid TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
        """
    )
    role_uuid = new_uuid()
    conn.execute("INSERT INTO roles(uuid, nombre) VALUES(?, 'gerente')", (role_uuid,))
    conn.commit()
    return conn, role_uuid


def test_event_has_required_contract():
    pub = PermissionEventPublisher()
    pub.publish(
        "ROLE_PERMISSIONS_UPDATED",
        operation_id=new_uuid(), entity_id=new_uuid(), user_name="admin",
        payload={"branch_id": new_uuid()},
    )
    event = pub.published_events[-1]
    for field in REQUIRED_EVENT_FIELDS:
        assert field in event, f"missing {field}"
    assert event["source_module"] == "CONFIGURATION"
    assert event["schema_version"] == 1
    # distinct UUIDv7 identifiers
    for field in UUID_FIELDS:
        assert UUID(event[field]).version == 7
    assert event["event_id"] != event["operation_id"] != event["entity_id"]


def test_event_rejects_integer_ids():
    pub = PermissionEventPublisher()
    with pytest.raises(ValueError):
        pub.publish("USER_PERMISSIONS_UPDATED", operation_id=new_uuid(),
                    entity_id=new_uuid(), user_name="a", payload={"branch_id": 1})
    with pytest.raises(ValueError):
        pub.publish("USER_PERMISSIONS_UPDATED", operation_id="op-legacy",
                    entity_id=new_uuid(), user_name="a", payload={"branch_id": new_uuid()})


class _SpyConn:
    def __init__(self, real, log):
        self._real = real
        self._log = log

    def __getattr__(self, n):
        return getattr(self._real, n)

    def commit(self):
        self._log.append("commit")
        return self._real.commit()


class _RecPub(PermissionEventPublisher):
    def __init__(self, log):
        super().__init__()
        self._log = log

    def publish(self, *a, **k):
        self._log.append("publish")
        return super().publish(*a, **k)


def test_event_post_commit():
    conn, role_uuid = _conn()
    log: list[str] = []
    svc = ModuleAccessService(ConfigRepository(_SpyConn(conn, log)), _RecPub(log))
    svc.save_role_permissions(role_uuid, {("POS", "ver"): True},
                              operation_id=new_uuid(), actor="admin")
    assert log[0] == "commit"
    assert log.count("commit") == 1 and log.count("publish") == 2
    assert log.index("commit") < log.index("publish")


def test_operation_id_idempotency():
    conn, role_uuid = _conn()
    pub = PermissionEventPublisher()
    svc = ModuleAccessService(ConfigRepository(conn), pub)
    op = new_uuid()
    svc.save_role_permissions(role_uuid, {("POS", "ver"): True}, operation_id=op, actor="admin")
    svc.save_role_permissions(role_uuid, {("POS", "ver"): True}, operation_id=op, actor="admin")
    # replayed command emits no second batch of events
    assert len(pub.published_events) == 2


def test_duplicate_operation_does_not_duplicate_permissions():
    conn, role_uuid = _conn()
    svc = ModuleAccessService(ConfigRepository(conn), PermissionEventPublisher())
    op = new_uuid()
    perms = {("POS", "ver"): True, ("CAJA", "ver"): True}
    svc.save_role_permissions(role_uuid, perms, operation_id=op, actor="admin")
    svc.save_role_permissions(role_uuid, perms, operation_id=op, actor="admin")
    count = conn.execute("SELECT COUNT(*) FROM rol_permisos WHERE rol_uuid=?", (role_uuid,)).fetchone()[0]
    assert count == 2
