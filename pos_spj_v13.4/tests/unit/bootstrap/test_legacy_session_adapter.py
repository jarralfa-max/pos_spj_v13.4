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


def test_warehouse_and_multi_branch_fields_default_empty_not_invented():
    adapter = LegacySessionAdapter(_context())
    assert adapter.active_warehouse_id == ""
    assert adapter.active_warehouse_name == ""
    assert adapter.sucursales_disponibles == []


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
