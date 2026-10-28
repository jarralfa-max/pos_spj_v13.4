"""Ámbito de los roles y capacidades del sitio, sin base de datos (auditoría
enterprise, Fase 2)."""

from __future__ import annotations

from datetime import date

from backend.application.security.access_scope import AccessScopeResolver
from backend.domain.organization.org_unit import Capability
from backend.domain.organization.role_assignment import (
    RoleAssignment,
    RoleAssignmentError,
    effective_on,
)
from backend.domain.organization.site_capabilities import (
    blocked_permission_families,
    module_allowed,
)

import pytest


class _Repo:
    def __init__(self, rol, propia, asignadas=(), extra=(), arbol=None):
        self._rol, self._propia, self._asignadas, self._extra = rol, propia, asignadas, extra
        self._arbol = arbol or {}

    def user_role_name(self, user_id):
        return self._rol

    def home_branch_id(self, user_id):
        return self._propia

    def assigned_branch_ids(self, user_id):
        return tuple(self._asignadas)

    def role_assignments(self, user_id):
        return tuple(self._extra)

    def site_ids_under(self, unit_id):
        return frozenset(self._arbol.get(unit_id, ()))


def _fila(rol, tipo, ambito, desde=None, hasta=None):
    return {"id": "a", "role_name": rol, "scope_type": tipo, "scope_id": ambito,
            "valid_from": desde, "valid_until": hasta}


def test_primary_scope_is_home_plus_assigned_and_full_access_is_company_wide():
    r = AccessScopeResolver(_Repo("cajero", "A", ("B",)))
    assert r.roles_at("u", "A") == ("cajero",) and r.roles_at("u", "C") == ()
    assert r.reach("u").site_ids == {"A", "B"}
    assert AccessScopeResolver(_Repo("admin", None)).reach("u").company_wide


def test_org_unit_assignments_inherit_down_the_hierarchy():
    r = AccessScopeResolver(_Repo("cajero", "A", extra=[_fila("gerente", "ORG_UNIT", "R")],
                                  arbol={"R": {"B", "C"}}))
    assert r.roles_at("u", "B") == ("gerente",)
    assert r.roles_at("u", "A") == ("cajero",)


def test_validity_window_is_inclusive():
    hoy = date(2026, 10, 25)
    r = AccessScopeResolver(_Repo("x", None, extra=[
        _fila("g", "COMPANY", "E", "2026-10-25", "2026-10-25")]), today=lambda: hoy)
    assert r.roles_at("u", "Z") == ("g",)
    assert not effective_on("2026-10-26", None, hoy) and not effective_on(None, "2026-10-24", hoy)


def test_a_repository_without_scopes_keeps_the_previous_behavior():
    class _Viejo:
        def user_role_name(self, user_id):
            return "cajero"
    assert not AccessScopeResolver(_Viejo()).supports_scopes


def test_assignment_entity_rules():
    with pytest.raises(RoleAssignmentError, match="ámbito"):
        RoleAssignment.create(user_id="u", role_id="r", scope_type="COMPANY", scope_id="",
                              reason="x")
    a = RoleAssignment.create(user_id="u", role_id="r", scope_type="ORG_UNIT", scope_id="s",
                              reason="Cobertura", valid_until=date(2026, 12, 31))
    assert a.is_effective(date(2026, 12, 31)) and not a.is_effective(date(2027, 1, 1))
    a.revoke(by="v", reason="Terminó")
    assert not a.is_effective(date(2026, 11, 1))
    with pytest.raises(RoleAssignmentError):
        a.revoke(by="v", reason="otra")


def test_site_capability_mapping():
    planta = frozenset({Capability.PRODUCTION.value, Capability.INVENTORY.value})
    assert not module_allowed("sales_pos", planta) and module_allowed("meat_processing", planta)
    assert module_allowed("products", planta)          # no depende del sitio
    assert module_allowed("sales_pos", None)           # sitio no gobernado
    bloqueadas = blocked_permission_families(planta)
    assert {"DELIVERY", "COMPRAS", "FINANZAS"} <= bloqueadas and "PRODUCCION" not in bloqueadas
