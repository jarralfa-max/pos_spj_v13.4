"""CRM-29 — SessionContext.tiene_permiso soporta wildcard de módulo
("CLIENTES.*"), no solo el código exacto y el wildcard global ("*")."""
from __future__ import annotations

from core.session_context import SessionContext


def _session_with(permisos) -> SessionContext:
    s = SessionContext()
    s.set_permisos(set(permisos))
    return s


def test_exact_permission_still_matches():
    s = _session_with({"CLIENTES.VER"})
    assert s.tiene_permiso("CLIENTES.VER") is True
    assert s.tiene_permiso("CLIENTES.EDITAR") is False


def test_global_wildcard_still_matches_everything():
    s = _session_with({"*"})
    assert s.tiene_permiso("CLIENTES.VER") is True
    assert s.tiene_permiso("CUALQUIER.COSA") is True


def test_module_wildcard_grants_every_action_in_module():
    s = _session_with({"CLIENTES.*"})
    assert s.tiene_permiso("CLIENTES.VER") is True
    assert s.tiene_permiso("CLIENTES.EDITAR") is True
    assert s.tiene_permiso("CLIENTES.CREDITO") is True


def test_module_wildcard_does_not_leak_to_other_modules():
    s = _session_with({"CLIENTES.*"})
    assert s.tiene_permiso("CRM.LEADS.VER") is False
    assert s.tiene_permiso("FINANZAS.VER") is False


def test_no_permisos_denies_everything():
    s = _session_with(set())
    assert s.tiene_permiso("CLIENTES.VER") is False


def test_admin_bypasses_regardless_of_permisos():
    s = _session_with(set())
    s._rol = "admin"
    assert s.tiene_permiso("CUALQUIER.COSA") is True
