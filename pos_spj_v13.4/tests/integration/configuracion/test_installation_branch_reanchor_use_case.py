"""SDLC-ARQ-TERM-002 · `SetInstallationBranchUseCase`: permiso en backend, guardas,
candado y auditoría — una prueba por regla, contra el esquema real."""
from __future__ import annotations

import json

import pytest

from backend.application.commands.settings_commands import SetInstallationBranchCommand
from backend.application.configuracion.authorization import (
    ConfiguracionAuthorizationPolicy,
    SessionPermissionChecker,
)
from backend.application.configuracion.permissions import ConfiguracionPermissions
from backend.application.use_cases.set_installation_branch_use_case import (
    SetInstallationBranchUseCase,
)
from backend.domain.settings.exceptions import (
    ConfigurationAuthorizationConfigurationError,
    ConfigurationPermissionDeniedError,
    InstallationBranchChangeRejectedError,
)
from backend.infrastructure.db.repositories.settings.installation_branch_unit_of_work import (
    InstallationBranchUnitOfWork,
)
from backend.shared.ids import new_uuid
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


class _Session:
    """Sesión mínima que `SessionPermissionChecker` entiende."""

    def __init__(self, permisos=()) -> None:
        self.user_id = new_uuid()
        self.is_active = True
        self._permisos = set(permisos)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permisos


def _uc(conn, session=None, *, policy=None):
    if policy is None and session is not None:
        policy = ConfiguracionAuthorizationPolicy(SessionPermissionChecker(session))
    return SetInstallationBranchUseCase(lambda: InstallationBranchUnitOfWork(conn), policy)


def _cmd(session, branch_id, operation_id=None):
    return SetInstallationBranchCommand(
        operation_id=operation_id or new_uuid(), branch_id=branch_id,
        user_name=session.user_id, workstation_id="CAJA-01")


@pytest.fixture
def autorizado():
    return _Session({ConfiguracionPermissions.ESTACION_REANCLAR})


# ── R1 · permiso en backend ─────────────────────────────────────────────
def test_editing_the_company_is_not_enough(conn):
    antes = s.ancla(conn)
    destino = s.sucursal(conn, "Norte")
    sesion = _Session({ConfiguracionPermissions.EMPRESA_EDITAR})
    with pytest.raises(ConfigurationPermissionDeniedError):
        _uc(conn, sesion).execute(_cmd(sesion, destino))
    assert s.ancla(conn) == antes
    [fila] = s.auditoria(conn)
    assert "resultado=RECHAZADO" in fila["detalles"]
    assert "motivo=PERMISSION_DENIED" in fila["detalles"]
    assert fila["usuario"] == sesion.user_id


@pytest.mark.unwired_fails_closed
def test_without_a_wired_policy_it_fails_closed(conn):
    antes = s.ancla(conn)
    destino = s.sucursal(conn, "Norte")
    sesion = _Session()
    with pytest.raises(ConfigurationAuthorizationConfigurationError):
        SetInstallationBranchUseCase(lambda: InstallationBranchUnitOfWork(conn)).execute(
            _cmd(sesion, destino))
    assert s.ancla(conn) == antes


def test_another_users_session_cannot_lend_its_permission(conn, autorizado):
    destino = s.sucursal(conn, "Norte")
    intruso = _Session()
    with pytest.raises(ConfigurationPermissionDeniedError):
        _uc(conn, autorizado).execute(_cmd(intruso, destino))


# ── R2 · registro central ───────────────────────────────────────────────
def test_an_enrolled_station_is_reassigned_by_the_central_registry(conn, autorizado):
    antes = s.ancla(conn)
    s.vincular_central(conn, antes)
    destino = s.sucursal(conn, "Norte")
    with pytest.raises(InstallationBranchChangeRejectedError) as exc:
        _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    assert exc.value.code == "CENTRAL_APPROVAL_REQUIRED"
    assert "registro central" in str(exc.value)
    assert s.ancla(conn) == antes
    assert "motivo=CENTRAL_APPROVAL_REQUIRED" in s.auditoria(conn)[-1]["detalles"]


def test_without_a_central_registry_the_local_permission_is_enough(conn, autorizado):
    destino = s.sucursal(conn, "Norte")
    _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    assert s.ancla(conn) == destino


# ── R3 · turno abierto ──────────────────────────────────────────────────
def test_an_open_shift_blocks_the_change(conn, autorizado):
    antes = s.ancla(conn)
    s.turno(conn, antes, "OPEN")
    destino = s.sucursal(conn, "Norte")
    with pytest.raises(InstallationBranchChangeRejectedError) as exc:
        _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    assert exc.value.code == "OPEN_CASH_SHIFT"
    assert "turno" in str(exc.value)
    assert s.ancla(conn) == antes
    [fila] = s.auditoria(conn)
    assert "motivo=OPEN_CASH_SHIFT" in fila["detalles"]
    assert json.loads(fila["valor_antes"])["branch_id"] == antes


def test_closed_or_cancelled_shifts_do_not_block(conn, autorizado):
    antes = s.ancla(conn)
    s.turno(conn, antes, "CLOSED")
    s.turno(conn, antes, "CANCELLED")
    destino = s.sucursal(conn, "Norte")
    _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    assert s.ancla(conn) == destino


# ── R4 · pendientes de sincronizar ──────────────────────────────────────
@pytest.mark.parametrize("state", ["RETRY", "CONFLICT"])
def test_unsynced_envelopes_block_the_change(conn, autorizado, state):
    antes = s.ancla(conn)
    s.sobre(conn, s.estacion(conn, antes), state)
    destino = s.sucursal(conn, "Norte")
    with pytest.raises(InstallationBranchChangeRejectedError) as exc:
        _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    assert exc.value.code == "PENDING_SYNC"
    assert s.ancla(conn) == antes


def test_an_unstaged_fact_blocks_the_change(conn, autorizado):
    antes = s.ancla(conn)
    s.estacion(conn, antes)
    s.hecho_en_outbox(conn)
    destino = s.sucursal(conn, "Norte")
    with pytest.raises(InstallationBranchChangeRejectedError) as exc:
        _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    assert exc.value.code == "PENDING_SYNC"


def test_only_synced_or_dead_envelopes_let_it_through(conn, autorizado):
    station = s.estacion(conn, s.ancla(conn))
    s.sobre(conn, station, "SYNCED", seq=1)
    s.sobre(conn, station, "DEAD", seq=2)
    destino = s.sucursal(conn, "Norte")
    _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    assert s.ancla(conn) == destino


# ── R5/R6 · éxito atómico y auditado ────────────────────────────────────
def test_success_writes_the_anchor_and_its_audit_row(conn, autorizado):
    antes = s.ancla(conn)
    destino = s.sucursal(conn, "Norte")
    operation_id = new_uuid()
    result = _uc(conn, autorizado).execute(_cmd(autorizado, destino, operation_id))
    assert result.success and result.entity_id == destino
    assert result.data == {"branch_name": "Norte", "previous_branch_id": antes,
                           "changed": True}
    assert s.ancla(conn) == destino
    [fila] = s.auditoria(conn)
    assert (fila["modulo"], fila["entidad"], fila["entidad_id"], fila["sucursal_id"]) == (
        "CONFIGURACION", "instalacion", destino, destino)
    assert fila["usuario"] == autorizado.user_id
    assert json.loads(fila["valor_antes"])["branch_id"] == antes
    assert json.loads(fila["valor_despues"]) == {"branch_id": destino, "branch_name": "Norte"}
    for parte in ("terminal=CAJA-01", "resultado=APLICADO", f"operation_id={operation_id}"):
        assert parte in fila["detalles"]


def test_success_is_committed_and_survives_a_rollback(conn, autorizado):
    destino = s.sucursal(conn, "Norte")
    _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    conn.rollback()
    assert s.ancla(conn) == destino and len(s.auditoria(conn)) == 1


def test_a_failed_audit_rolls_the_anchor_back(conn, autorizado, monkeypatch):
    from backend.infrastructure.db.repositories.settings.audit_log_repository import (
        SqliteAuditLogRepository,
    )

    antes = s.ancla(conn)
    destino = s.sucursal(conn, "Norte")

    def _falla(self, **kwargs):
        raise RuntimeError("audit_logs no disponible")

    monkeypatch.setattr(SqliteAuditLogRepository, "record", _falla)
    with pytest.raises(RuntimeError):
        _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    assert s.ancla(conn) == antes


# ── R7 · idempotencia y validación ──────────────────────────────────────
def test_re_anchoring_to_the_current_branch_is_a_no_op(conn, autorizado):
    destino = s.sucursal(conn, "Norte")
    uc = _uc(conn, autorizado)
    uc.execute(_cmd(autorizado, destino))
    segundo = uc.execute(_cmd(autorizado, destino))
    assert segundo.data["changed"] is False
    assert len(s.auditoria(conn)) == 1


def test_an_unknown_or_inactive_branch_is_still_rejected(conn, autorizado):
    antes = s.ancla(conn)
    with pytest.raises(ValueError, match="activa"):
        _uc(conn, autorizado).execute(_cmd(autorizado, new_uuid()))
    with pytest.raises(ValueError, match="activa"):
        _uc(conn, autorizado).execute(_cmd(autorizado, s.sucursal(conn, "Baja", activa=0)))
    assert s.ancla(conn) == antes


def test_repairing_a_missing_anchor_is_allowed_and_audited(conn, autorizado):
    s.quitar_ancla(conn)
    destino = s.sucursal(conn, "Norte")
    result = _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    assert result.data["previous_branch_id"] == "" and s.ancla(conn) == destino
    assert json.loads(s.auditoria(conn)[0]["valor_antes"]) == {}


def test_repairing_still_blocks_on_an_open_shift_anywhere_else(conn, autorizado):
    otra = s.sucursal(conn, "Otra")
    s.turno(conn, otra, "OPEN")
    s.quitar_ancla(conn)
    destino = s.sucursal(conn, "Norte")
    with pytest.raises(InstallationBranchChangeRejectedError) as exc:
        _uc(conn, autorizado).execute(_cmd(autorizado, destino))
    assert exc.value.code == "OPEN_CASH_SHIFT"
    assert s.ancla(conn) is None


# ── la segunda puerta ya no existe ──────────────────────────────────────
def test_the_company_profile_service_no_longer_writes_the_anchor():
    from backend.application.configuracion.settings_services import CompanyProfileService

    assert not hasattr(CompanyProfileService, "set_installation_branch")
