from .refactor_control_helpers import ALLOWED_STATES, load_refactor_state, parse_queue_modules


def test_module_queue_is_complete_in_refactor_state():
    queue_modules = parse_queue_modules()
    state_modules = load_refactor_state()["modules"]
    missing = sorted(set(queue_modules) - set(state_modules))
    extra = sorted(set(state_modules) - set(queue_modules))
    assert not missing
    assert not extra


def test_module_queue_uses_only_allowed_states():
    invalid = {code: status for code, status in parse_queue_modules().items() if status not in ALLOWED_STATES}
    assert not invalid
