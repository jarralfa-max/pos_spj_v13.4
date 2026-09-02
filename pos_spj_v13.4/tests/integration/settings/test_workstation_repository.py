"""SET-6 — SqliteWorkstationRepository against a real (in-memory) SQLite
born-clean schema.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationStatus, WorkstationType
from backend.infrastructure.db.repositories.settings.workstation_repository import (
    SqliteWorkstationRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

_NOW = datetime.now(timezone.utc)


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def repo(conn):
    return SqliteWorkstationRepository(conn)


def _existing_branch_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    return branch_id


class TestWorkstationRepository:
    def test_round_trips_all_fields(self, conn, repo):
        branch_id = _existing_branch_id(conn)
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS,
            device_identifier="MAC-AA:BB:CC", operating_system="Windows 11",
            application_version="13.4.0", offline_enabled=False,
        )
        workstation.check_in(at=_NOW)
        repo.save(workstation)
        conn.commit()

        fetched = repo.get(workstation.id)
        assert fetched.id == workstation.id
        assert fetched.branch_id == branch_id
        assert fetched.code == "POS-01"
        assert fetched.workstation_type is WorkstationType.POS
        assert fetched.device_identifier == "MAC-AA:BB:CC"
        assert fetched.application_version == "13.4.0"
        assert fetched.offline_enabled is False
        assert fetched.last_seen_at == _NOW.isoformat(timespec="seconds")
        assert fetched.status is WorkstationStatus.ACTIVE

    def test_branch_id_must_reference_existing_sucursal(self, conn, repo):
        orphan = Workstation.create(
            branch_id=new_uuid(), code="POS-99", name="Fantasma", workstation_type=WorkstationType.POS,
        )
        with pytest.raises(sqlite3.IntegrityError):
            repo.save(orphan)
            conn.commit()
        conn.rollback()

    def test_code_uniqueness_enforced(self, conn, repo):
        branch_id_a, branch_id_b = _existing_branch_id(conn), _existing_branch_id(conn)
        repo.save(Workstation.create(
            branch_id=branch_id_a, code="POS-01", name="A", workstation_type=WorkstationType.POS,
        ))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            repo.save(Workstation.create(
                branch_id=branch_id_b, code="POS-01", name="B", workstation_type=WorkstationType.POS,
            ))
            conn.commit()
        conn.rollback()

    def test_get_by_code(self, conn, repo):
        branch_id = _existing_branch_id(conn)
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="A", workstation_type=WorkstationType.POS,
        )
        repo.save(workstation)
        conn.commit()
        assert repo.get_by_code("POS-01").id == workstation.id
        assert repo.get_by_code("MISSING") is None

    def test_list_by_branch(self, conn, repo):
        branch_id_a, branch_id_b = _existing_branch_id(conn), _existing_branch_id(conn)
        repo.save(Workstation.create(
            branch_id=branch_id_a, code="POS-01", name="A1", workstation_type=WorkstationType.POS,
        ))
        repo.save(Workstation.create(
            branch_id=branch_id_a, code="BO-01", name="A2", workstation_type=WorkstationType.BACKOFFICE,
        ))
        repo.save(Workstation.create(
            branch_id=branch_id_b, code="POS-02", name="B1", workstation_type=WorkstationType.POS,
        ))
        conn.commit()
        results = repo.list_by_branch(branch_id_a)
        assert [w.code for w in results] == ["BO-01", "POS-01"]

    def test_list_active_excludes_non_active_states(self, conn, repo):
        branch_id = _existing_branch_id(conn)
        active = Workstation.create(
            branch_id=branch_id, code="POS-01", name="Activa", workstation_type=WorkstationType.POS,
        )
        blocked = Workstation.create(
            branch_id=branch_id, code="POS-02", name="Bloqueada", workstation_type=WorkstationType.POS,
        )
        blocked.block("motivo")
        retired = Workstation.create(
            branch_id=branch_id, code="POS-03", name="Retirada", workstation_type=WorkstationType.POS,
        )
        retired.retire()
        repo.save(active)
        repo.save(blocked)
        repo.save(retired)
        conn.commit()

        results = repo.list_active()
        assert [w.code for w in results] == ["POS-01"]

    def test_update_via_save_upsert_preserves_status_transitions(self, conn, repo):
        branch_id = _existing_branch_id(conn)
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="A", workstation_type=WorkstationType.POS,
        )
        repo.save(workstation)
        conn.commit()

        workstation.block("reporte de uso indebido")
        repo.save(workstation)
        conn.commit()

        fetched = repo.get(workstation.id)
        assert fetched.status is WorkstationStatus.BLOCKED
        assert fetched.blocked_reason == "reporte de uso indebido"

    def test_without_check_in_last_seen_at_is_none(self, conn, repo):
        branch_id = _existing_branch_id(conn)
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="A", workstation_type=WorkstationType.POS,
        )
        repo.save(workstation)
        conn.commit()
        assert repo.get(workstation.id).last_seen_at is None
