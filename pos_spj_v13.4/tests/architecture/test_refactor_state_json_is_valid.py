from .refactor_control_helpers import ALLOWED_STATES, REFACTOR_DIR, load_refactor_state


def test_refactor_state_json_is_valid_and_uses_allowed_states():
    state = load_refactor_state()
    assert state["global_status"] in {"IN_PROGRESS", "DONE", "BLOCKED"}
    assert state["current_module"] in state["modules"]
    invalid = {
        code: module.get("status")
        for code, module in state["modules"].items()
        if module.get("status") not in ALLOWED_STATES
    }
    assert not invalid


def test_done_modules_are_complete():
    state = load_refactor_state()
    incomplete_done = {}
    for code, module in state["modules"].items():
        if module.get("status") != "DONE":
            continue
        report_path = REFACTOR_DIR.parent.parent / module["report"]
        if not (
            module.get("score") == 100
            and module.get("open_violations") == 0
            and module.get("tests_failed") == 0
            and report_path.is_file()
        ):
            incomplete_done[code] = module
    assert not incomplete_done
