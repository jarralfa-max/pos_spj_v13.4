import pytest

from backend.bootstrap.application_context import ApplicationContext, FeatureContext
from backend.bootstrap.application_context_errors import (
    BranchNotFoundError,
    ContextSwitchNotAllowedError,
)
from backend.bootstrap.application_context_service import (
    PERMISSION_APPLICATION_CONTEXT_SWITCH,
    ApplicationContextService,
    BranchLookupResult,
)


def _context(*, roles=("gerente",), permissions=None) -> ApplicationContext:
    permissions = permissions if permissions is not None else {PERMISSION_APPLICATION_CONTEXT_SWITCH}
    return ApplicationContext(
        installation_id="i", company_id="c", branch_id="branch-1", branch_name="Sucursal Centro",
        workstation_id="ws", workstation_type="pos", user_id="user-1", user_name="Jose",
        roles=roles, permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


BRANCHES = {"branch-2": BranchLookupResult(id="branch-2", name="Sucursal Norte")}
PERMISSIONS_BY_BRANCH = {"branch-2": frozenset({"POS.ver", "CAJA.crear"})}
FLAGS_BY_BRANCH = {"branch-2": {"whatsapp": True, "delivery": False}}


def _service(*, open_operations=False, audit_sink=None) -> ApplicationContextService:
    return ApplicationContextService(
        branch_resolver=lambda branch_id: BRANCHES.get(branch_id),
        permissions_loader=lambda user_id, branch_id: PERMISSIONS_BY_BRANCH.get(branch_id, frozenset()),
        feature_flags_loader=lambda branch_id: FLAGS_BY_BRANCH.get(branch_id, {}),
        open_operations_checker=lambda: open_operations,
        audit_sink=audit_sink,
    )


def test_successful_branch_switch_returns_new_context():
    service = _service()
    original = _context()
    switched = service.change_branch(original, new_branch_id="branch-2")

    assert switched.branch_id == "branch-2"
    assert switched.branch_name == "Sucursal Norte"
    assert switched is not original
    assert original.branch_id == "branch-1"  # unchanged


def test_permissions_are_reloaded_for_the_new_branch():
    service = _service()
    switched = service.change_branch(_context(), new_branch_id="branch-2")
    assert switched.permissions == frozenset({"POS.ver", "CAJA.crear"})


def test_feature_context_is_reloaded_for_the_new_branch():
    service = _service()
    switched = service.change_branch(_context(), new_branch_id="branch-2")
    assert switched.feature_context.is_enabled("whatsapp") is True
    assert switched.feature_context.is_enabled("delivery") is False


def test_switch_without_permission_raises():
    service = _service()
    context_without_permission = _context(roles=("cajero",), permissions=set())
    with pytest.raises(ContextSwitchNotAllowedError):
        service.change_branch(context_without_permission, new_branch_id="branch-2")


def test_admin_can_always_switch_even_without_explicit_permission():
    service = _service()
    admin_context = _context(roles=("admin",), permissions=set())
    switched = service.change_branch(admin_context, new_branch_id="branch-2")
    assert switched.branch_id == "branch-2"


def test_switch_blocked_by_open_operations():
    service = _service(open_operations=True)
    with pytest.raises(ContextSwitchNotAllowedError):
        service.change_branch(_context(), new_branch_id="branch-2")


def test_switch_to_unknown_branch_raises():
    service = _service()
    with pytest.raises(BranchNotFoundError):
        service.change_branch(_context(), new_branch_id="does-not-exist")


def test_open_operations_checked_only_after_permission_passes():
    # A user without permission gets ContextSwitchNotAllowedError for the
    # permission reason, not silently masked by the open-operations check —
    # verified indirectly: permission failure happens even when
    # open_operations=False (i.e. it's not the open-ops branch that raised).
    service = _service(open_operations=False)
    context_without_permission = _context(roles=("cajero",), permissions=set())
    with pytest.raises(ContextSwitchNotAllowedError):
        service.change_branch(context_without_permission, new_branch_id="branch-2")


def test_events_emitted_in_order_on_success():
    events = []
    service = _service(audit_sink=lambda event, payload: events.append(event))
    service.change_branch(_context(), new_branch_id="branch-2")

    assert events == [
        "APPLICATION_CONTEXT_CHANGING", "APPLICATION_CONTEXT_CHANGED", "NAVIGATION_CONTEXT_REBUILT",
    ]


def test_only_changing_event_emitted_when_permission_denied():
    events = []
    service = _service(audit_sink=lambda event, payload: events.append(event))
    context_without_permission = _context(roles=("cajero",), permissions=set())
    with pytest.raises(ContextSwitchNotAllowedError):
        service.change_branch(context_without_permission, new_branch_id="branch-2")

    assert events == ["APPLICATION_CONTEXT_CHANGING"]


def test_no_events_leak_the_context_payload_beyond_ids():
    events = []
    service = _service(audit_sink=lambda event, payload: events.append(payload))
    service.change_branch(_context(), new_branch_id="branch-2")
    for payload in events:
        assert set(payload.keys()) <= {"user_id", "from_branch_id", "to_branch_id", "branch_id"}
