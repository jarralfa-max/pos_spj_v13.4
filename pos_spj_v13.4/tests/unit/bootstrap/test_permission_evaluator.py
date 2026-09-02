import pytest

from backend.bootstrap.application_context import ApplicationContext, FeatureContext
from backend.bootstrap.permission_evaluator import PermissionEvaluator


def _context(*, roles=("cajero",), permissions=frozenset()) -> ApplicationContext:
    return ApplicationContext(
        installation_id="i", company_id="c", branch_id="b", branch_name="Sucursal",
        workstation_id="ws", workstation_type="pos", user_id="u", user_name="Usuario",
        roles=roles, permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="s",
    )


def test_admin_bypasses_everything():
    evaluator = PermissionEvaluator(_context(roles=("admin",), permissions=frozenset()))
    assert evaluator.has_permission("ANYTHING.NOT_GRANTED") is True


def test_system_owner_bypasses_everything():
    evaluator = PermissionEvaluator(_context(roles=("system_owner",)))
    assert evaluator.has_permission("ANYTHING.NOT_GRANTED") is True


def test_exact_permission_match():
    evaluator = PermissionEvaluator(_context(permissions=frozenset({"POS.VER"})))
    assert evaluator.has_permission("POS.ver") is True  # normalized, case-insensitive


def test_missing_permission_denied():
    evaluator = PermissionEvaluator(_context(permissions=frozenset({"POS.VER"})))
    assert evaluator.has_permission("POS.eliminar") is False


def test_module_wildcard_grants_any_action_in_that_module():
    evaluator = PermissionEvaluator(_context(permissions=frozenset({"CLIENTES.*"})))
    assert evaluator.has_permission("CLIENTES.ver") is True
    assert evaluator.has_permission("CLIENTES.eliminar") is True
    assert evaluator.has_permission("POS.ver") is False


def test_global_wildcard_grants_everything():
    evaluator = PermissionEvaluator(_context(permissions=frozenset({"*"})))
    assert evaluator.has_permission("ANYTHING.here") is True


def test_require_permission_raises_when_denied():
    evaluator = PermissionEvaluator(_context(permissions=frozenset()))
    with pytest.raises(PermissionError):
        evaluator.require_permission("POS.ver")


def test_require_permission_silent_when_granted():
    evaluator = PermissionEvaluator(_context(permissions=frozenset({"POS.VER"})))
    evaluator.require_permission("POS.ver")  # must not raise


def test_no_permissions_denies_non_admin():
    evaluator = PermissionEvaluator(_context(roles=("cajero",), permissions=frozenset()))
    assert evaluator.has_permission("POS.ver") is False
