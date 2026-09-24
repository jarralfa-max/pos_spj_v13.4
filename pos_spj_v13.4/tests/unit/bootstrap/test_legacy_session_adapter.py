import pytest

from backend.bootstrap.application_context import ApplicationContext, FeatureContext
from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter


def _context(*, roles=("cajero",), permissions=frozenset(), **overrides) -> ApplicationContext:
    kwargs = dict(
        installation_id="install-1", company_id="company-1", branch_id="branch-1",
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id="user-1", user_name="Juan Perez", roles=roles,
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )
    kwargs.update(overrides)
    return ApplicationContext(**kwargs)


def test_identity_fields_map_from_the_context():
    adapter = LegacySessionAdapter(_context())
    assert adapter.user_id == "user-1"
    assert adapter.usuario == "Juan Perez"
    assert adapter.nombre_completo == "Juan Perez"
    assert adapter.sucursal_id == "branch-1"
    assert adapter.active_branch_id == "branch-1"
    assert adapter.sucursal_nombre == "Sucursal Centro"
    assert adapter.is_branch_resolved is True


def test_rol_is_the_first_role_or_empty():
    assert LegacySessionAdapter(_context(roles=("gerente", "cajero"))).rol == "gerente"
    assert LegacySessionAdapter(_context(roles=())).rol == ""


def test_is_active_is_always_true_for_an_authenticated_context():
    assert LegacySessionAdapter(_context()).is_active is True


def test_es_admin_matches_application_context_is_admin():
    assert LegacySessionAdapter(_context(roles=("admin",))).es_admin is True
    assert LegacySessionAdapter(_context(roles=("cajero",))).es_admin is False


def test_es_gerente_matches_legacy_role_list():
    assert LegacySessionAdapter(_context(roles=("gerente",))).es_gerente is True
    assert LegacySessionAdapter(_context(roles=("gerente_rh",))).es_gerente is True
    assert LegacySessionAdapter(_context(roles=("cajero",))).es_gerente is False


def test_warehouse_fields_default_empty_not_invented():
    adapter = LegacySessionAdapter(_context())
    assert adapter.active_warehouse_id == ""
    assert adapter.active_warehouse_name == ""
    # `sucursales_disponibles` sigue vacío A PROPÓSITO: pretendía ser la lista
    # (id + nombre) para un SELECTOR de sucursal, no el conjunto de alcance, y
    # ninguna pantalla la consume. No confundir con `assigned_branch_ids`.
    assert adapter.sucursales_disponibles == []


def test_assigned_branches_default_to_empty_without_assignments():
    """Vacío significa "sin asignaciones explícitas", NO "ninguna sucursal":
    quien no tiene filas en `usuarios_sucursales` opera en la suya."""
    assert LegacySessionAdapter(_context()).assigned_branch_ids == frozenset()


def test_assigned_branches_use_the_name_the_execution_contexts_read():
    """El NOMBRE importa más que el valor.

    `resolve_inventory_execution_context` —y sus equivalentes de Mermas y
    Cárnico— buscan `assigned_branch_ids` (o el alias en español) por `getattr`.
    Si no coincidiera, resolverían el conjunto vacío EN SILENCIO y el nivel
    "sucursales asignadas" del alcance seguiría sin poder conceder nada a nadie,
    que es exactamente como estuvo hasta el 2026-09-17: el atributo se leía y
    NINGÚN objeto de sesión lo escribía.
    """
    adapter = LegacySessionAdapter(
        _context(assigned_branch_ids=frozenset({"b2", "b3"})))
    assert adapter.assigned_branch_ids == frozenset({"b2", "b3"})
    assert adapter.sucursales_asignadas == frozenset({"b2", "b3"})


def test_assigned_branches_reach_the_inventory_execution_context():
    """Extremo a extremo del cableado, no sólo de la propiedad: que el dato
    llegue y que además CONCEDA alcance sobre la sucursal asignada."""
    from backend.application.inventory.execution_context import (
        resolve_inventory_execution_context,
    )
    from backend.domain.inventory.exceptions import BranchScopeError

    adapter = LegacySessionAdapter(_context(assigned_branch_ids=frozenset({"b2"})))
    context = resolve_inventory_execution_context(adapter)

    assert context.assigned_branch_ids == frozenset({"b2"})
    context.enforce_branch("branch-1")   # la propia: siempre permitida
    context.enforce_branch("b2")         # asignada: ahora sí concede
    with pytest.raises(BranchScopeError):
        context.enforce_branch("b9")     # ajena: sigue bloqueada


def test_assigned_branches_survive_a_branch_change():
    """`ApplicationContext.with_branch()` reconstruye el contexto campo por
    campo, así que un campo que no se nombre allí se pierde EN SILENCIO justo
    al cambiar de sucursal — la operación donde el alcance más importa. Vive
    aquí, junto al resto del contrato de sesión, para que no se pierda."""
    context = _context(assigned_branch_ids=frozenset({"b2", "b3"}))

    movido = context.with_branch(
        branch_id="b2", branch_name="Centro", permissions=frozenset(),
        feature_context=FeatureContext())

    assert movido.assigned_branch_ids == frozenset({"b2", "b3"})


def test_permisos_passes_through_the_context_permission_set():
    adapter = LegacySessionAdapter(_context(permissions=frozenset({"POS.VER"})))
    assert adapter.permisos == frozenset({"POS.VER"})


def test_tiene_permiso_exact_match_case_insensitive():
    adapter = LegacySessionAdapter(_context(permissions=frozenset({"POS.VER"})))
    assert adapter.tiene_permiso("POS.ver") is True
    assert adapter.tiene_permiso("POS.eliminar") is False


def test_tiene_permiso_module_wildcard():
    adapter = LegacySessionAdapter(_context(permissions=frozenset({"CLIENTES.*"})))
    assert adapter.tiene_permiso("CLIENTES.ver") is True
    assert adapter.tiene_permiso("POS.ver") is False


def test_tiene_permiso_admin_bypasses_everything():
    adapter = LegacySessionAdapter(_context(roles=("admin",), permissions=frozenset()))
    assert adapter.tiene_permiso("ANYTHING.NOT_GRANTED") is True


def test_requiere_permiso_raises_when_denied():
    adapter = LegacySessionAdapter(_context(permissions=frozenset()))
    with pytest.raises(PermissionError):
        adapter.requiere_permiso("POS.ver")


def test_requiere_permiso_silent_when_granted():
    adapter = LegacySessionAdapter(_context(permissions=frozenset({"POS.VER"})))
    adapter.requiere_permiso("POS.ver")  # must not raise


def test_to_dict_reflects_current_fields():
    adapter = LegacySessionAdapter(_context(permissions=frozenset({"POS.VER"})))
    d = adapter.to_dict()
    assert d["user_id"] == "user-1"
    assert d["sucursal_id"] == "branch-1"
    assert d["n_permisos"] == 1


def test_has_no_mutation_methods_the_immutable_context_cannot_support():
    adapter = LegacySessionAdapter(_context())
    assert not hasattr(adapter, "set_user")
    assert not hasattr(adapter, "set_sucursal")
    assert not hasattr(adapter, "clear")
