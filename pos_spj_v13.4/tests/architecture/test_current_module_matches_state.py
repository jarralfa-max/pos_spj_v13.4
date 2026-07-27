from .refactor_control_helpers import load_refactor_state, parse_current_module_code, parse_queue_modules


def test_current_module_matches_json_state_and_queue():
    state = load_refactor_state()
    current_from_markdown = parse_current_module_code()
    assert current_from_markdown == state["current_module"]
    assert current_from_markdown in parse_queue_modules()


def test_exactly_one_current_module_is_defined():
    state = load_refactor_state()
    current = state.get("current_module")
    assert isinstance(current, str) and current
    assert list(state["modules"]).count(current) == 1
