"""UUIDv7 identity integrity tests for the CONFIGURACION module.

Protects the canonical identity contract required by REGLA CERO:
- branch persistence mints and round-trips a canonical UUIDv7 (never an int),
- event label resolvers return names instead of exposing integer ids,
- the permission event publisher rejects non-UUIDv7 / integer identities,
- ``backend.shared.ids.new_uuid`` is the single UUIDv7 generator and the
  configuration repository never falls back to ``uuid4``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

from backend.shared.ids import new_uuid
from core.services.configuration_settings_service import (
    CompanyProfileService,
    PermissionEventPublisher,
)
from repositories.config_repository import ConfigRepository

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _canonical_branch_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, "
        "nombre TEXT, direccion TEXT, telefono TEXT, activa INTEGER)"
    )
    return conn


def test_new_uuid_is_canonical_uuidv7() -> None:
    value = new_uuid()
    parsed = UUID(value)
    assert parsed.version == 7
    assert value == value.lower()


def test_save_branch_mints_uuidv7_and_round_trips() -> None:
    service = CompanyProfileService(ConfigRepository(_canonical_branch_conn()))

    branch_id = service.save_branch(name="Centro", address="MX", phone="+5215500000000", active=True)

    assert UUID(branch_id).version == 7
    branch = service.get_branch(branch_id)
    assert branch is not None
    assert branch["uuid"] == branch_id
    assert branch["nombre"] == "Centro"


def test_update_branch_keeps_same_uuid_identity() -> None:
    service = CompanyProfileService(ConfigRepository(_canonical_branch_conn()))
    branch_id = service.save_branch(name="Centro", address="MX", phone="+520000", active=True)

    same_id = service.save_branch(
        name="Centro Norte", address="MX", phone="+520001", active=True, branch_id=branch_id
    )

    assert same_id == branch_id
    assert service.get_branch(branch_id)["nombre"] == "Centro Norte"


def test_event_label_resolvers_return_names_not_integer_ids() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT);
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, descripcion TEXT);
        INSERT INTO usuarios(usuario) VALUES('ana');
        INSERT INTO roles(nombre, descripcion) VALUES('gerente', 'Gerente');
        """
    )
    repository = ConfigRepository(conn)

    assert repository.username_for_id(1) == "ana"
    assert repository.role_name_for_id(1) == "gerente"
    assert repository.username_for_id(999) is None


def test_label_resolvers_prefer_uuid_when_available() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    branch_uuid = new_uuid()
    conn.execute("CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT)")
    conn.execute("INSERT INTO roles(uuid, nombre) VALUES(?, ?)", (branch_uuid, "supervisor"))

    repository = ConfigRepository(conn)
    assert repository.role_name_for_id(branch_uuid) == "supervisor"


def test_permission_publisher_rejects_integer_branch_identity() -> None:
    publisher = PermissionEventPublisher()
    try:
        publisher.publish(
            "USER_PERMISSIONS_UPDATED",
            operation_id=new_uuid(),
            entity_id=new_uuid(),
            user_name="admin",
            payload={"branch_id": 1},
        )
    except ValueError as exc:
        assert "branch_id" in str(exc)
    else:
        raise AssertionError("integer branch_id must be rejected by the publisher")


def test_permission_publisher_rejects_legacy_operation_id() -> None:
    publisher = PermissionEventPublisher()
    try:
        publisher.publish(
            "ROLE_PERMISSIONS_UPDATED",
            operation_id="op-save",
            entity_id=new_uuid(),
            user_name="admin",
            payload={"branch_id": new_uuid()},
        )
    except ValueError as exc:
        assert "operation_id" in str(exc)
    else:
        raise AssertionError("legacy operation_id strings must be rejected")


def test_config_repository_has_no_uuid4_generator() -> None:
    content = (PACKAGE_ROOT / "repositories" / "config_repository.py").read_text(encoding="utf-8")
    assert "uuid4" not in content
    assert "from backend.shared.ids import new_uuid" in content
