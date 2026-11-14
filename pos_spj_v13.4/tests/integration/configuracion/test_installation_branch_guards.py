"""SDLC-ARQ-TERM-002 · consultas de guarda del re-anclaje, contra el esquema real."""
from __future__ import annotations

import pytest

from backend.infrastructure.db.repositories.settings.installation_branch_repository import (
    SqliteInstallationBranchRepository,
)
from backend.infrastructure.db.repositories.settings.installation_branch_unit_of_work import (
    InstallationBranchUnitOfWork,
)
from tests.integration.configuracion import _reanchor_support as s


@pytest.fixture(scope="module")
def template():
    conn = s.build_template()
    yield conn
    conn.close()


@pytest.fixture
def conn(template):
    copia = s.copy_of(template)
    yield copia
    copia.close()


@pytest.fixture
def repo(conn):
    return SqliteInstallationBranchRepository(conn)


# ── turnos ──────────────────────────────────────────────────────────────
def test_unfinished_shifts_outside_the_target_are_counted(conn, repo):
    actual = s.ancla(conn)
    destino = s.sucursal(conn, "Norte")
    for status in ("OPEN", "SUSPENDED", "COUNTING", "CLOSING"):
        s.turno(conn, actual, status)
    assert repo.open_cash_shifts_outside(destino) == 4


def test_finished_shifts_and_shifts_at_the_target_do_not_count(conn, repo):
    actual = s.ancla(conn)
    destino = s.sucursal(conn, "Norte")
    for status in ("CLOSED", "FORCE_CLOSED", "CANCELLED"):
        s.turno(conn, actual, status)
    s.turno(conn, destino, "OPEN")
    assert repo.open_cash_shifts_outside(destino) == 0


# ── sincronización ──────────────────────────────────────────────────────
def test_without_a_replication_station_nothing_is_pending(conn, repo):
    s.hecho_en_outbox(conn)
    assert repo.pending_sync_count() == 0


@pytest.mark.parametrize("state", ["PENDING", "IN_FLIGHT", "RETRY", "CONFLICT"])
def test_unsettled_envelopes_are_pending(conn, repo, state):
    s.sobre(conn, s.estacion(conn, s.ancla(conn)), state)
    assert repo.pending_sync_count() == 1


def test_synced_and_dead_envelopes_are_final(conn, repo):
    station = s.estacion(conn, s.ancla(conn))
    s.sobre(conn, station, "SYNCED", seq=1)
    s.sobre(conn, station, "DEAD", seq=2)
    assert repo.pending_sync_count() == 0


def test_an_outbox_fact_without_envelope_is_pending(conn, repo):
    s.estacion(conn, s.ancla(conn))
    s.hecho_en_outbox(conn)
    assert repo.pending_sync_count() == 1


# ── registro central ────────────────────────────────────────────────────
def test_without_the_enrollment_table_there_is_no_central_registry(conn, repo):
    assert repo.central_enrollment_active() is False


def test_an_enrolled_station_is_under_the_central_registry(conn, repo):
    s.vincular_central(conn, s.ancla(conn))
    assert repo.central_enrollment_active() is True


def test_a_superseded_enrollment_does_not_count(conn, repo):
    s.vincular_central(conn, s.ancla(conn), status="SUPERSEDED")
    assert repo.central_enrollment_active() is False


# ── unidad de trabajo ───────────────────────────────────────────────────
def test_the_unit_of_work_rolls_back_anchor_and_audit_together(conn):
    antes = s.ancla(conn)
    destino = s.sucursal(conn, "Norte")
    with pytest.raises(RuntimeError):
        with InstallationBranchUnitOfWork(conn) as uow:
            uow.installation_branch.set(destino)
            uow.audit_log.record(action="instalacion.reanclar", entity="instalacion",
                                 entity_id=destino)
            raise RuntimeError("falla a mitad")
    assert s.ancla(conn) == antes
    assert s.auditoria(conn) == []
